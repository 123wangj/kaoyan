(function () {
  function init() {
    const form = document.getElementById('schoolSelectionForm');
    if (!form || form.dataset.ready === 'true') return;
    form.dataset.ready = 'true';
    form.addEventListener('submit', async function (event) {
      event.preventDefault();
      await window.runSchoolSelectionAnalysis();
    });
  }

  window.KaoyanSchoolSelectionView = { init };
})();
