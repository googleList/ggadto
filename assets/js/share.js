(function () {
  "use strict";

  function shareUrl(network, pageUrl, pageTitle) {
    var url = encodeURIComponent(pageUrl);
    var title = encodeURIComponent(pageTitle);
    var targets = {
      facebook: "https://www.facebook.com/sharer/sharer.php?u=" + url,
      x: "https://x.com/intent/post?url=" + url + "&text=" + title,
      linkedin: "https://www.linkedin.com/sharing/share-offsite/?url=" + url,
      telegram: "https://t.me/share/url?url=" + url + "&text=" + title
    };
    return targets[network] || pageUrl;
  }

  function setupShareLinks() {
    var canonical = document.querySelector('link[rel="canonical"]');
    var pageUrl = canonical ? canonical.href : window.location.href;
    var pageTitle = document.title || "RankLab";
    var links = document.querySelectorAll("[data-share-network]");

    links.forEach(function (link) {
      var network = link.getAttribute("data-share-network");
      link.setAttribute("href", shareUrl(network, pageUrl, pageTitle));
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupShareLinks);
  } else {
    setupShareLinks();
  }
})();
