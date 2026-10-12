(function (window) {
    "use strict";

    var $ = window.jQuery;
    if (!$ || !$.fn || typeof $.fn.owlCarousel !== "function") {
        return;
    }

    /* Restore slides from pages saved after Owl had already initialized. */
    $(".owl-carousel.owl-loaded").each(function () {
        var $carousel = $(this);
        var $stage = $carousel.children(".owl-stage-outer").children(".owl-stage");
        if (!$stage.length) return;

        var $slides = $stage.children(".owl-item").not(".cloned").children().clone();
        if (!$slides.length) return;

        $carousel.empty()
            .removeClass("owl-loaded owl-drag owl-hidden")
            .removeAttr("style")
            .append($slides);
    });

    $(".testi-list-1").owlCarousel({
        loop: true, autoplay: true, autoplayTimeout: 10000, dots: true, nav: true,
        navText: ["‹", "›"],
        responsive: {0: {items: 1}, 480: {items: 1}, 600: {items: 1}, 768: {items: 1}, 992: {items: 1}, 1000: {items: 1}, 1920: {items: 1}}
    });
    $(".testi-list-2").owlCarousel({
        loop: true, autoplay: true, autoplayTimeout: 10000, dots: true, nav: false, margin: 10,
        navText: ["‹", "›"],
        responsive: {0: {items: 1}, 480: {items: 1}, 600: {items: 1}, 768: {items: 2}, 992: {items: 2}, 1000: {items: 3}, 1920: {items: 4}}
    });
    $(".testi-list-3").owlCarousel({
        loop: true, autoplay: true, autoplayTimeout: 10000, dots: false, nav: true, margin: 30,
        navText: ["‹", "›"],
        responsive: {0: {items: 1}, 480: {items: 1}, 600: {items: 1}, 768: {items: 1}, 992: {items: 2}, 1000: {items: 2}, 1920: {items: 2}}
    });
    $(".brand-list-1").owlCarousel({
        loop: true, autoplay: true, autoplayTimeout: 10000, dots: false, nav: false,
        navText: ["‹", "›"],
        responsive: {0: {items: 1}, 480: {items: 2}, 600: {items: 2}, 768: {items: 3}, 992: {items: 4}, 1000: {items: 5}, 1920: {items: 6}}
    });
    $(".brand-list-2").owlCarousel({
        loop: true, autoplay: true, autoplayTimeout: 10000, dots: false, nav: false,
        navText: ["‹", "›"],
        responsive: {0: {items: 1}, 480: {items: 2}, 600: {items: 2}, 768: {items: 3}, 992: {items: 4}, 1000: {items: 5}, 1920: {items: 5}}
    });
    $(".project-list").owlCarousel({
        loop: true, dots: false, nav: false, margin: 30,
        navText: ["‹", "›"],
        responsive: {0: {items: 1}, 480: {items: 1}, 600: {items: 1}, 768: {items: 2}, 992: {items: 3}, 1000: {items: 3}, 1365: {items: 4}, 1920: {items: 4}}
    });
    $(".blog-list-2").owlCarousel({
        loop: true, autoplay: true, autoplayTimeout: 10000, dots: false, nav: true, margin: 30,
        navText: ["‹", "›"],
        responsive: {0: {items: 1}, 480: {items: 1}, 600: {items: 1}, 768: {items: 2}, 992: {items: 2}, 1000: {items: 3}, 1920: {items: 3}}
    });
    $(".blog-list-3").owlCarousel({
        loop: true, autoplay: true, autoplayTimeout: 10000, dots: true, nav: false, margin: 30,
        navText: ["‹", "›"],
        responsive: {0: {items: 1}, 480: {items: 1}, 600: {items: 1}, 768: {items: 2}, 992: {items: 2}, 1000: {items: 3}, 1920: {items: 3}}
    });

    function initProjectGrid() {
        if ($.fn.isotope) {
            var $grid = $(".image_load");
            $grid.isotope({
                itemSelector: ".grid-item", filter: "*", resizesContainer: true,
                layoutMode: "masonry", transitionDuration: "0.8s"
            });
            $(".menu-filtering li").on("click", function () {
                $(".menu-filtering li").removeClass("current_menu_item");
                $(this).addClass("current_menu_item");
                $grid.isotope({filter: $(this).attr("data-filter")});
            });
        }
    }

    if ($.fn.imagesLoaded) {
        $(".image_load").imagesLoaded(initProjectGrid);
    } else {
        initProjectGrid();
    }
})(window);
