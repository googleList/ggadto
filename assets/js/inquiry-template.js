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
        status.textContent = "请先填写需要咨询的项目，再复制。";
        field.focus();
        return;
      }
      button.disabled = true;
      button.textContent = "正在复制";
      status.textContent = "";
      try {
        if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error("clipboard-unavailable");
        await navigator.clipboard.writeText(content);
        status.textContent = "已复制。请在 Telegram 粘贴并核对内容，再发送。";
      } catch (error) {
        field.focus();
        field.select();
        field.setSelectionRange(0, field.value.length);
        status.textContent = "浏览器未允许自动复制，已选中模板，请手动复制。";
      } finally {
        button.disabled = false;
        button.textContent = "复制咨询模板";
      }
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setupInquiryTemplate);
  else setupInquiryTemplate();
})();
