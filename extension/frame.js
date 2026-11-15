// Browser Glass companion, in every frame of a web page. A page shown
// inside another one (an embedded sign-in, a consent dialog, a video
// player, a comment box) keeps its own look: the glass styles skip a
// document whose <html> carries data-browserglass-off, set here at once
// and again whenever the page replaces <html> or takes the mark off. The
// top page is left to content.js.
"use strict";

if (window !== window.top) {
  const OFF = "data-browserglass-off";
  let watched = null;
  const keep = () => {
    const root = document.documentElement;
    if (!root)
      return;
    if (!root.hasAttribute(OFF))
      root.setAttribute(OFF, "");
    if (root !== watched) {
      watched = root;
      rootAttrs.observe(root, {attributes: true, attributeFilter: [OFF]});
    }
  };
  const rootAttrs = new MutationObserver(keep);
  new MutationObserver(keep).observe(document, {childList: true});
  keep();
}
