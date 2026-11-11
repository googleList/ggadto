(function () {
  "use strict";
  function setupInquiryTemplate() {
    var field = document.getElementById("inquiry-template");
    var button = document.getElementById("copy-inquiry-template");
    var status = document.getElementById("inquiry-copy-status");
    if (!field || !button || !status) return;
    button.hidden = false;
    field.addEventListener("input", function () {
      status.textContent = "";
    });
    button.addEventListener("click", async function () {
      var content = field.value.trim();
      if (!content) {
        status.textContent = "Fill in the project details before copying.";
        field.focus();
        return;
      }
      button.disabled = true;
      button.textContent = "Copying…";
      status.textContent = "";
      try {
        if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error("clipboard-unavailable");
        await navigator.clipboard.writeText(content);
        status.textContent = "Copied. Paste into Telegram and check the details before sending.";
      } catch (error) {
        field.focus();
        field.select();
        field.setSelectionRange(0, field.value.length);
        status.textContent = "Automatic copying was blocked. Copy the selected template manually.";
      } finally {
        button.disabled = false;
        button.textContent = "Copy inquiry template";
      }
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setupInquiryTemplate);
  else setupInquiryTemplate();
})();
