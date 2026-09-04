import { useCallback, useEffect, useRef, useState } from "react";

/** One lifecycle for a trigger and its portalled reading surface. */
export function useHoverDisclosure(openDelay = 300, closeDelay = 300) {
  const [visible, setVisible] = useState(false);
  const opening = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closing = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancel = useCallback(() => {
    if (opening.current) clearTimeout(opening.current);
    if (closing.current) clearTimeout(closing.current);
    opening.current = closing.current = null;
  }, []);
  useEffect(() => cancel, [cancel]);
  const retain = useCallback(() => {
    cancel();
    setVisible(true);
  }, [cancel]);
  const enter = useCallback(() => {
    cancel();
    opening.current = setTimeout(() => {
      opening.current = null;
      setVisible(true);
    }, openDelay);
  }, [cancel, openDelay]);
  const leave = useCallback(() => {
    if (opening.current) clearTimeout(opening.current);
    opening.current = null;
    // Repeated pointer movement outside must not postpone dismissal forever.
    if (!closing.current) closing.current = setTimeout(() => {
      closing.current = null;
      setVisible(false);
    }, closeDelay);
  }, [closeDelay]);
  const dismiss = useCallback(() => {
    cancel();
    setVisible(false);
  }, [cancel]);
  useEffect(() => {
    if (!visible) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [visible, dismiss]);
  return { visible, enter, retain, leave, dismiss };
}
