import React from "react";
import { api } from "../api.js";

// Iframe of the backend's slide preview: the same HTML that ends up in the exports.
// The revision and theme go in the query string so a saved edit or a theme change reloads the frame.
export default function SlideFrame({ deckId, slide, theme, title, inert = false }) {
  return (
    <div className={inert ? "slide-frame slide-frame-inert" : "slide-frame"}>
      <iframe
        src={api.slidePreviewUrl(deckId, slide.id, slide.revision, theme)}
        title={inert ? undefined : title}
        aria-hidden={inert ? "true" : undefined}
        tabIndex={inert ? -1 : undefined}
        loading="lazy"
      />
    </div>
  );
}
