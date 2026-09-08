(() => {
  const sections = [...document.querySelectorAll("main section[id]")];
  const navLinks = [...document.querySelectorAll("nav a[href^='#']")];

  if ("IntersectionObserver" in window && sections.length) {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];

        if (!visible) return;

        navLinks.forEach((link) => {
          const active = link.getAttribute("href") === `#${visible.target.id}`;
          link.toggleAttribute("aria-current", active);
        });
      },
      { rootMargin: "-25% 0px -65% 0px", threshold: [0, 0.2, 0.6] },
    );

    sections.forEach((section) => observer.observe(section));
  }

  const mapTabs = [...document.querySelectorAll("[data-map-view]")];
  const mapPanels = [...document.querySelectorAll("[data-map-panel]")];

  const activateMap = (name, focus = false) => {
    mapTabs.forEach((tab) => {
      const active = tab.dataset.mapView === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active && focus) tab.focus();
    });

    mapPanels.forEach((panel) => {
      const active = panel.dataset.mapPanel === name;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
  };

  mapTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateMap(tab.dataset.mapView));
    tab.addEventListener("keydown", (event) => {
      const keyMoves = { ArrowRight: 1, ArrowLeft: -1 };
      if (!(event.key in keyMoves) && !["Home", "End"].includes(event.key)) return;

      event.preventDefault();
      let next = index + (keyMoves[event.key] || 0);
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = mapTabs.length - 1;
      next = (next + mapTabs.length) % mapTabs.length;
      activateMap(mapTabs[next].dataset.mapView, true);
    });
  });
})();
