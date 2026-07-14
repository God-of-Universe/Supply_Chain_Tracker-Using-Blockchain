document.addEventListener("DOMContentLoaded", () => {
  const items = document.querySelectorAll(".timeline li");

  const isInViewport = el => {
    const rect = el.getBoundingClientRect();
    return (
      rect.top <= (window.innerHeight || document.documentElement.clientHeight)
    );
  };

  const run = () =>
    items.forEach(item => {
      if (isInViewport(item)) {
        item.classList.add("show");
      }
    });

  // Run initially and on scroll
  run();
  window.addEventListener("scroll", run);
});
