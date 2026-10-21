(function ($) {
  "use strict";
  if (!$) return;
  $(function () {
    if ($.fn.meanmenu) {
      $(".mobile-menu nav").meanmenu({
        meanScreenWidth: "991",
        meanMenuContainer: ".mobile-menu",
        meanMenuOpen: "<span></span> <span></span> <span></span>",
        onePage: false
      });
    }
    $(document).on("click", ".search-box-outer", function () {
      $("body").addClass("search-active");
    });
    $(document).on("click", ".close-search", function () {
      $("body").removeClass("search-active");
    });
    var lastRun = 0;
    var timer;
    function updateHeader() {
      lastRun = Date.now();
      $("#sticky-header").toggleClass("sticky", $(window).scrollTop() >= 100);
    }
    $(window).on("scroll", function () {
      var remaining = 200 - (Date.now() - lastRun);
      clearTimeout(timer);
      if (remaining <= 0) updateHeader();
      else timer = setTimeout(updateHeader, remaining);
    });
    updateHeader();
    function markLoaded() {
      $("body").addClass("loaded");
      $(".loader").fadeOut(500);
    }
    if (document.readyState === "complete") markLoaded();
    else $(window).one("load", markLoaded);
  });
})(window.jQuery);
