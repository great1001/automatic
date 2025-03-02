import base64
import io
import os
import re

from PIL import Image
import gradio as gr
from modules.paths import data_path
from modules import shared, ui_tempdir, script_callbacks, images

re_param_code = r'\s*([\w ]+):\s*("(?:\\"[^,]|\\"|\\|[^\"])+"|[^,]*)(?:,|$)'
re_param = re.compile(re_param_code)
re_imagesize = re.compile(r"^(\d+)x(\d+)$")
re_hypernet_hash = re.compile("\(([0-9a-f]+)\)$") # pylint: disable=anomalous-backslash-in-string
type_of_gr_update = type(gr.update())

paste_fields = {}
registered_param_bindings = []


class ParamBinding:
    def __init__(self, paste_button, tabname, source_text_component=None, source_image_component=None, source_tabname=None, override_settings_component=None, paste_field_names=[]):
        self.paste_button = paste_button
        self.tabname = tabname
        self.source_text_component = source_text_component
        self.source_image_component = source_image_component
        self.source_tabname = source_tabname
        self.override_settings_component = override_settings_component
        self.paste_field_names = paste_field_names


def reset():
    paste_fields.clear()


def quote(text):
    if ',' not in str(text):
        return text
    text = str(text)
    text = text.replace('\\', '\\\\')
    text = text.replace('"', '\\"')
    return f'"{text}"'


def image_from_url_text(filedata):
    if filedata is None:
        return None
    if type(filedata) == list and len(filedata) > 0 and type(filedata[0]) == dict and filedata[0].get("is_file", False):
        filedata = filedata[0]
    if type(filedata) == dict and filedata.get("is_file", False):
        filename = filedata["name"]
        is_in_right_dir = ui_tempdir.check_tmp_file(shared.demo, filename)
        if is_in_right_dir:
            image = Image.open(filename)
            geninfo, _items = images.read_info_from_image(image)
            image.info['parameters'] = geninfo
            return image
        else:
            shared.log.warning(f'File access denied: {filename}')
            return None
    if type(filedata) == list:
        if len(filedata) == 0:
            return None
        filedata = filedata[0]
    if type(filedata) == dict:
        shared.log.warning('Incorrect filedata received')
        return None
    if filedata.startswith("data:image/png;base64,"):
        filedata = filedata[len("data:image/png;base64,"):]
    if filedata.startswith("data:image/webp;base64,"):
        filedata = filedata[len("data:image/webp;base64,"):]
    if filedata.startswith("data:image/jpeg;base64,"):
        filedata = filedata[len("data:image/jpeg;base64,"):]
    filedata = base64.decodebytes(filedata.encode('utf-8'))
    image = Image.open(io.BytesIO(filedata))
    images.read_info_from_image(image)
    return image


def add_paste_fields(tabname, init_img, fields, override_settings_component=None):
    paste_fields[tabname] = {"init_img": init_img, "fields": fields, "override_settings_component": override_settings_component}

    # backwards compatibility for existing extensions
    import modules.ui
    if tabname == 'txt2img':
        modules.ui.txt2img_paste_fields = fields
    elif tabname == 'img2img':
        modules.ui.img2img_paste_fields = fields


def create_buttons(tabs_list):
    buttons = {}
    for tab in tabs_list:
        name = tab
        if name == 'txt2img':
            name = 'text'
        elif name == 'img2img':
            name = 'image'
        elif name == 'extras':
            name = 'process'
        buttons[tab] = gr.Button(f"➠ {name}", elem_id=f"{tab}_tab")
    return buttons


def bind_buttons(buttons, send_image, send_generate_info):
    """old function for backwards compatibility; do not use this, use register_paste_params_button"""
    for tabname, button in buttons.items():
        source_text_component = send_generate_info if isinstance(send_generate_info, gr.components.Component) else None
        source_tabname = send_generate_info if isinstance(send_generate_info, str) else None
        register_paste_params_button(ParamBinding(paste_button=button, tabname=tabname, source_text_component=source_text_component, source_image_component=send_image, source_tabname=source_tabname))


def register_paste_params_button(binding: ParamBinding):
    registered_param_bindings.append(binding)


def connect_paste_params_buttons():
    binding: ParamBinding
    for binding in registered_param_bindings:
        destination_image_component = paste_fields[binding.tabname]["init_img"]
        fields = paste_fields[binding.tabname]["fields"]
        override_settings_component = binding.override_settings_component or paste_fields[binding.tabname]["override_settings_component"]
        destination_width_component = next(iter([field for field, name in fields if name == "Size-1"] if fields else []), None)
        destination_height_component = next(iter([field for field, name in fields if name == "Size-2"] if fields else []), None)

        if binding.source_image_component and destination_image_component:
            if isinstance(binding.source_image_component, gr.Gallery):
                func = send_image_and_dimensions if destination_width_component else image_from_url_text
                jsfunc = "extract_image_from_gallery"
            else:
                func = send_image_and_dimensions if destination_width_component else lambda x: x
                jsfunc = None
            binding.paste_button.click(
                fn=func,
                _js=jsfunc,
                inputs=[binding.source_image_component],
                outputs=[destination_image_component, destination_width_component, destination_height_component] if destination_width_component else [destination_image_component],
            )
        if binding.source_text_component is not None and fields is not None:
            connect_paste(binding.paste_button, fields, binding.source_text_component, override_settings_component, binding.tabname)
        if binding.source_tabname is not None and fields is not None:
            paste_field_names = ['Prompt', 'Negative prompt', 'Steps', 'Face restoration'] + (["Seed"] if shared.opts.send_seed else []) + binding.paste_field_names
            binding.paste_button.click(
                fn=lambda *x: x,
                inputs=[field for field, name in paste_fields[binding.source_tabname]["fields"] if name in paste_field_names],
                outputs=[field for field, name in fields if name in paste_field_names],
            )
        binding.paste_button.click(
            fn=None,
            _js=f"switch_to_{binding.tabname}",
            inputs=[],
            outputs=[],
        )


def send_image_and_dimensions(x):
    if isinstance(x, Image.Image):
        img = x
    else:
        img = image_from_url_text(x)
    if shared.opts.send_size and isinstance(img, Image.Image):
        w = img.width
        h = img.height
    else:
        w = gr.update()
        h = gr.update()
    return img, w, h



def find_hypernetwork_key(hypernet_name, hypernet_hash=None):
    """Determines the config parameter name to use for the hypernet based on the parameters in the infotext.

    Example: an infotext provides "Hypernet: ke-ta" and "Hypernet hash: 1234abcd". For the "Hypernet" config
    parameter this means there should be an entry that looks like "ke-ta-10000(1234abcd)" to set it to.

    If the infotext has no hash, then a hypernet with the same name will be selected instead.
    """
    hypernet_name = hypernet_name.lower()
    if hypernet_hash is not None:
        # Try to match the hash in the name
        for hypernet_key in shared.hypernetworks.keys():
            result = re_hypernet_hash.search(hypernet_key)
            if result is not None and result[1] == hypernet_hash:
                return hypernet_key
    else:
        # Fall back to a hypernet with the same name
        for hypernet_key in shared.hypernetworks.keys():
            if hypernet_key.lower().startswith(hypernet_name):
                return hypernet_key

    return None


def restore_old_hires_fix_params(res):
    """for infotexts that specify old First pass size parameter, convert it into
    width, height, and hr scale"""

    firstpass_width = res.get('First pass size-1', None)
    firstpass_height = res.get('First pass size-2', None)

    if shared.opts.use_old_hires_fix_width_height:
        hires_width = int(res.get("Hires resize-1", 0))
        hires_height = int(res.get("Hires resize-2", 0))

        if hires_width and hires_height:
            res['Size-1'] = hires_width
            res['Size-2'] = hires_height
            return

    if firstpass_width is None or firstpass_height is None:
        return

    firstpass_width, firstpass_height = int(firstpass_width), int(firstpass_height)
    width = int(res.get("Size-1", 512))
    height = int(res.get("Size-2", 512))

    if firstpass_width == 0 or firstpass_height == 0:
        from modules import processing
        firstpass_width, firstpass_height = processing.old_hires_fix_first_pass_dimensions(width, height)

    res['Size-1'] = firstpass_width
    res['Size-2'] = firstpass_height
    res['Hires resize-1'] = width
    res['Hires resize-2'] = height


def parse_generation_parameters(x: str):
    """parses generation parameters string, the one you see in text field under the picture in UI:
```
girl with an artist's beret, determined, blue eyes, desert scene, computer monitors, heavy makeup, by Alphonse Mucha and Charlie Bowater, ((eyeshadow)), (coquettish), detailed, intricate
Negative prompt: ugly, fat, obese, chubby, (((deformed))), [blurry], bad anatomy, disfigured, poorly drawn face, mutation, mutated, (extra_limb), (ugly), (poorly drawn hands), messy drawing
Steps: 20, Sampler: Euler a, CFG scale: 7, Seed: 965400086, Size: 512x512, Model hash: 45dee52b
```

    returns a dict with field values
    """
    res = {}
    prompt = ""
    negative_prompt = ""
    done_with_prompt = False
    *lines, lastline = x.strip().split("\n")
    if len(re_param.findall(lastline)) < 3:
        lines.append(lastline)
        lastline = ''
    for _i, line in enumerate(lines):
        line = line.strip()
        if line.startswith("Negative prompt:"):
            done_with_prompt = True
            line = line[16:].strip()
        if done_with_prompt:
            negative_prompt += ("" if negative_prompt == "" else "\n") + line
        else:
            prompt += ("" if prompt == "" else "\n") + line
    res["Prompt"] = prompt
    res["Negative prompt"] = negative_prompt
    for k, v in re_param.findall(lastline):
        v = v[1:-1] if v[0] == '"' and v[-1] == '"' else v
        m = re_imagesize.match(v)
        if m is not None:
            res[k+"-1"] = m.group(1)
            res[k+"-2"] = m.group(2)
        else:
            res[k] = v
    # Missing CLIP skip means it was set to 1 (the default)
    if "Clip skip" not in res:
        res["Clip skip"] = "1"
    hypernet = res.get("Hypernet", None)
    if hypernet is not None:
        res["Prompt"] += f"""<hypernet:{hypernet}:{res.get("Hypernet strength", "1.0")}>"""
    if "Hires resize-1" not in res:
        res["Hires resize-1"] = 0
        res["Hires resize-2"] = 0
    # Infer additional override settings for token merging
    token_merging_ratio = res.get("Token merging ratio", None)
    token_merging_ratio_hr = res.get("Token merging ratio hr", None)
    if token_merging_ratio is not None or token_merging_ratio_hr is not None:
        res["Token merging"] = 'True'
        if token_merging_ratio is None:
            res["Token merging hr only"] = 'True'
        else:
            res["Token merging hr only"] = 'False'
        if res.get("Token merging random", None) is None:
            res["Token merging random"] = 'False'
        if res.get("Token merging merge attention", None) is None:
            res["Token merging merge attention"] = 'True'
        if res.get("Token merging merge cross attention", None) is None:
            res["Token merging merge cross attention"] = 'False'
        if res.get("Token merging merge mlp", None) is None:
            res["Token merging merge mlp"] = 'False'
        if res.get("Token merging stride x", None) is None:
            res["Token merging stride x"] = '2'
        if res.get("Token merging stride y", None) is None:
            res["Token merging stride y"] = '2'

    restore_old_hires_fix_params(res)
    return res


settings_map = {}


infotext_to_setting_name_mapping = [
    ('Clip skip', 'CLIP_stop_at_last_layers', ),
    ('Conditional mask weight', 'inpainting_mask_weight'),
    ('Model hash', 'sd_model_checkpoint'),
    ('ENSD', 'eta_noise_seed_delta'),
    ('Noise multiplier', 'initial_noise_multiplier'),
    ('Eta', 'eta_ancestral'),
    ('Eta DDIM', 'eta_ddim'),
    ('Discard penultimate sigma', 'always_discard_next_to_last_sigma'),
    ('UniPC variant', 'uni_pc_variant'),
    ('UniPC skip type', 'uni_pc_skip_type'),
    ('UniPC order', 'uni_pc_order'),
    ('UniPC lower order final', 'uni_pc_lower_order_final'),
    ('Token merging', 'token_merging'),
    ('Token merging ratio', 'token_merging_ratio'),
    ('Token merging hr only', 'token_merging_hr_only'),
    ('Token merging ratio hr', 'token_merging_ratio_hr'),
    ('Token merging random', 'token_merging_random'),
    ('Token merging merge attention', 'token_merging_merge_attention'),
    ('Token merging merge cross attention', 'token_merging_merge_cross_attention'),
    ('Token merging merge mlp', 'token_merging_merge_mlp'),
    ('Token merging maximum downsampling', 'token_merging_maximum_down_sampling'),
    ('Token merging stride x', 'token_merging_stride_x'),
    ('Token merging stride y', 'token_merging_stride_y')
]


def create_override_settings_dict(text_pairs):
    """creates processing's override_settings parameters from gradio's multiselect
    Example input:
        ['Clip skip: 2', 'Model hash: e6e99610c4', 'ENSD: 31337']

    Example output:
        {'CLIP_stop_at_last_layers': 2, 'sd_model_checkpoint': 'e6e99610c4', 'eta_noise_seed_delta': 31337}
    """
    res = {}
    params = {}
    for pair in text_pairs:
        k, v = pair.split(":", maxsplit=1)
        params[k] = v.strip()
    for param_name, setting_name in infotext_to_setting_name_mapping:
        value = params.get(param_name, None)
        if value is None:
            continue
        res[setting_name] = shared.opts.cast_value(setting_name, value)
    return res


def connect_paste(button, local_paste_fields, input_comp, override_settings_component, tabname):
    def paste_func(prompt):
        if prompt is not None and 'Negative prompt' not in prompt and 'Steps' not in prompt:
            prompt = None
        if not prompt and not shared.cmd_opts.hide_ui_dir_config:
            filename = os.path.join(data_path, "params.txt")
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf8") as file:
                    prompt = file.read()
            else:
                prompt = ''
        params = parse_generation_parameters(prompt)
        script_callbacks.infotext_pasted_callback(prompt, params)
        res = []
        for output, key in local_paste_fields:
            if callable(key):
                v = key(params)
            else:
                v = params.get(key, None)
            if v is None:
                res.append(gr.update())
            elif isinstance(v, type_of_gr_update):
                res.append(v)
            else:
                try:
                    valtype = type(output.value)
                    if valtype == bool and v == "False":
                        val = False
                    else:
                        val = valtype(v)
                    res.append(gr.update(value=val))
                except Exception:
                    res.append(gr.update())
        return res

    if override_settings_component is not None:
        def paste_settings(params):
            vals = {}
            for param_name, setting_name in infotext_to_setting_name_mapping:
                v = params.get(param_name, None)
                if v is None:
                    continue
                if setting_name == "sd_model_checkpoint" and shared.opts.disable_weights_auto_swap:
                    continue
                v = shared.opts.cast_value(setting_name, v)
                current_value = getattr(shared.opts, setting_name, None)
                if v == current_value:
                    continue
                vals[param_name] = v
            vals_pairs = [f"{k}: {v}" for k, v in vals.items()]
            return gr.Dropdown.update(value=vals_pairs, choices=vals_pairs, visible=len(vals_pairs) > 0)
        local_paste_fields = local_paste_fields + [(override_settings_component, paste_settings)]

    button.click(
        fn=paste_func,
        inputs=[input_comp],
        outputs=[x[0] for x in local_paste_fields],
    )
    button.click(
        fn=None,
        _js=f"recalculate_prompts_{tabname}",
        inputs=[],
        outputs=[],
    )
