(function () {
  const buttons = document.querySelectorAll("[data-chapter-btn]");
  const chapters = document.querySelectorAll("[data-chapter]");
  const feedback = document.getElementById("quiz-feedback");

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-chapter-btn");
      buttons.forEach((b) => b.classList.toggle("active", b === btn));
      chapters.forEach((c) =>
        c.classList.toggle("active", c.getAttribute("data-chapter") === id)
      );
    });
  });

  document.querySelectorAll("[data-quiz]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ok = btn.getAttribute("data-quiz") === "correct";
      if (!feedback) return;
      feedback.textContent = ok
        ? "Correct — the linker is the bridge connecting warhead and E3."
        : "Not quite — warhead binds the target protein; E3 recruits the trash machinery; linker connects them.";
      feedback.style.color = ok ? "#136357" : "#d65a45";
    });
  });
})();
