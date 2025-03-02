let currentWidth = null;
let currentHeight = null;
let arFrameTimeout = setTimeout(() => {}, 0);

function dimensionChange(e, is_width, is_height) {
  if (is_width) {
    currentWidth = e.target.value * 1.0;
  }
  if (is_height) {
    currentHeight = e.target.value * 1.0;
  }

  const inImg2img = gradioApp().querySelector('#tab_img2img').style.display === 'block';

  if (!inImg2img) {
    return;
  }

  let targetElement = null;

  const tabIndex = get_tab_index('mode_img2img');
  if (tabIndex === 0) { // img2img
    targetElement = gradioApp().querySelector('#img2img_image div[data-testid=image] img');
  } else if (tabIndex === 1) { // Sketch
    targetElement = gradioApp().querySelector('#img2img_sketch div[data-testid=image] img');
  } else if (tabIndex === 2) { // Inpaint
    targetElement = gradioApp().querySelector('#img2maskimg div[data-testid=image] img');
  } else if (tabIndex === 3) { // Inpaint sketch
    targetElement = gradioApp().querySelector('#inpaint_sketch div[data-testid=image] img');
  }

  if (targetElement) {
    let arPreviewRect = gradioApp().querySelector('#imageARPreview');
    if (!arPreviewRect) {
      arPreviewRect = document.createElement('div');
      arPreviewRect.id = 'imageARPreview';
      gradioApp().appendChild(arPreviewRect);
    }

    const viewportOffset = targetElement.getBoundingClientRect();

    viewportscale = Math.min(targetElement.clientWidth / targetElement.naturalWidth, targetElement.clientHeight / targetElement.naturalHeight);

    scaledx = targetElement.naturalWidth * viewportscale;
    scaledy = targetElement.naturalHeight * viewportscale;

    cleintRectTop = (viewportOffset.top + window.scrollY);
    cleintRectLeft = (viewportOffset.left + window.scrollX);
    cleintRectCentreY = cleintRectTop + (targetElement.clientHeight / 2);
    cleintRectCentreX = cleintRectLeft + (targetElement.clientWidth / 2);

    viewRectTop = cleintRectCentreY - (scaledy / 2);
    viewRectLeft = cleintRectCentreX - (scaledx / 2);
    arRectWidth = scaledx;
    arRectHeight = scaledy;

    arscale = Math.min(arRectWidth / currentWidth, arRectHeight / currentHeight);
    arscaledx = currentWidth * arscale;
    arscaledy = currentHeight * arscale;

    arRectTop = cleintRectCentreY - (arscaledy / 2);
    arRectLeft = cleintRectCentreX - (arscaledx / 2);
    arRectWidth = arscaledx;
    arRectHeight = arscaledy;

    arPreviewRect.style.top = `${arRectTop}px`;
    arPreviewRect.style.left = `${arRectLeft}px`;
    arPreviewRect.style.width = `${arRectWidth}px`;
    arPreviewRect.style.height = `${arRectHeight}px`;

    clearTimeout(arFrameTimeout);
    arFrameTimeout = setTimeout(() => {
      arPreviewRect.style.display = 'none';
    }, 2000);
    arPreviewRect.style.display = 'block';
  }
}

onUiUpdate(() => {
  const arPreviewRect = gradioApp().querySelector('#imageARPreview');
  if (arPreviewRect) {
    arPreviewRect.style.display = 'none';
  }
  const tabImg2img = gradioApp().querySelector('#tab_img2img');
  if (tabImg2img) {
    const inImg2img = tabImg2img.style.display === 'block';
    if (inImg2img) {
      const inputs = gradioApp().querySelectorAll('input');
      inputs.forEach((e) => {
        const is_width = e.parentElement.id === 'img2img_width';
        const is_height = e.parentElement.id === 'img2img_height';

        if ((is_width || is_height) && !e.classList.contains('scrollwatch')) {
          e.addEventListener('input', (e) => { dimensionChange(e, is_width, is_height); });
          e.classList.add('scrollwatch');
        }
        if (is_width) {
          currentWidth = e.value * 1.0;
        }
        if (is_height) {
          currentHeight = e.value * 1.0;
        }
      });
    }
  }
});
