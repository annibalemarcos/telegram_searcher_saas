(function(){
    if (window.location.hash === "#debug") {
        const panel = document.getElementById("debug");
        if (panel) {
            setTimeout(() => panel.scrollIntoView({behavior:"smooth", block:"start"}), 120);
        }
    }
})();
