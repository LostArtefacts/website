document.addEventListener('DOMContentLoaded', () => {
  const themes = ['system', 'light', 'dark'];
  const themeLabels = {system: 'System', light: 'Light', dark: 'Dark'};

  function currentTheme() {
    const theme = document.documentElement.dataset.theme;
    return theme === 'light' || theme === 'dark' ? theme : 'system';
  }

  function labelToggle(button) {
    const theme = currentTheme();
    const next = themes[(themes.indexOf(theme) + 1) % themes.length];
    const label =
      'Theme: ' + themeLabels[theme] + ' (switch to ' + themeLabels[next] + ')';
    button.title = label;
    button.setAttribute('aria-label', label);
  }

  const themeToggles = document.querySelectorAll('[data-theme-toggle]');
  themeToggles.forEach((button) => {
    labelToggle(button);
    button.addEventListener('click', () => {
      const theme =
        themes[(themes.indexOf(currentTheme()) + 1) % themes.length];
      try {
        if (theme === 'system') {
          delete document.documentElement.dataset.theme;
          localStorage.removeItem('theme');
        } else {
          document.documentElement.dataset.theme = theme;
          localStorage.setItem('theme', theme);
        }
      } catch (e) {
      }
      themeToggles.forEach(labelToggle);
    });
  });

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
