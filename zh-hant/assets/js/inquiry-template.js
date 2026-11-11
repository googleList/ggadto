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
        status.textContent = "請先填寫需要諮詢的項目，再複製。";
        field.focus();
        return;
      }
      button.disabled = true;
      button.textContent = "正在複製";
      status.textContent = "";
      try {
        if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error("clipboard-unavailable");
        await navigator.clipboard.writeText(content);
        status.textContent = "已複製。請在 Telegram 粘貼並覈對內容，再發送。";
      } catch (error) {
        field.focus();
        field.select();
        field.setSelectionRange(0, field.value.length);
        status.textContent = "瀏覽器未允許自動複製，已選中模板，請手動複製。";
      } finally {
        button.disabled = false;
        button.textContent = "複製諮詢模板";
      }
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setupInquiryTemplate);
  else setupInquiryTemplate();
})();
