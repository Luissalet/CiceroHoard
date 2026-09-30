import { createContext, useContext, useEffect } from "react";

export const DeckContext = createContext(null);
export const useDeck = () => useContext(DeckContext);

// Editors call this with "has unsaved changes" so tab switches and page unloads can ask first.
export function useDirty(dirty) {
  const { dirtyRef } = useDeck();
  useEffect(() => {
    dirtyRef.current = !!dirty;
    return () => { dirtyRef.current = false; };
  }, [dirty, dirtyRef]);
}
