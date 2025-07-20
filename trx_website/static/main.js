document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.ba-slider').forEach((slider) => {
    const handle = slider.querySelector('.handle');
    const resize = slider.querySelector('.resize');
    let dragging = false;
    let sliderRect;

    function startDrag(e) {
      dragging = true;
      sliderRect = slider.getBoundingClientRect();
      e.preventDefault();
    }

    function stopDrag() {
      dragging = false;
    }

    function onDrag(e) {
      if (!dragging) {
        return;
      }
      const pageX = e.pageX || (e.touches && e.touches[0].pageX);
      let posX = pageX - sliderRect.left - window.scrollX;
      posX = Math.max(0, Math.min(posX, sliderRect.width));
      const percent = (posX / sliderRect.width) * 100;
      resize.style.clipPath = 'polygon(0 0, ' + percent + '% 0, ' + percent + '% 100%, 0 100%)';
      handle.style.left = percent + '%';
    }

    handle.addEventListener('mousedown', startDrag);
    handle.addEventListener('touchstart', startDrag);
    window.addEventListener('mouseup', stopDrag);
    window.addEventListener('touchend', stopDrag);
    window.addEventListener('mousemove', onDrag);
    window.addEventListener('touchmove', onDrag);
  });
});
