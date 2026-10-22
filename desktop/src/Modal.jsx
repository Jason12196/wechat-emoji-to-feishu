import { useEffect, useRef } from "react";
import { X } from "lucide-react";

export default function Modal({
  title,
  description,
  children,
  footer,
  onClose,
  wide = false,
  className = "",
}) {
  const ref = useRef(null);
  const closing = useRef(false);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    dialog.showModal();
    return () => {
      dialog.close();
      previous?.focus();
    };
  }, []);
  async function dismiss() {
    if (closing.current || !onClose) return;
    closing.current = true;
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    await ref.current.animate(
      [
        { opacity: 1, transform: "translateY(0) scale(1)" },
        {
          opacity: 0,
          transform: reduced ? "none" : "translateY(8px) scale(.985)",
        },
      ],
      { duration: reduced ? 0 : 150, easing: "ease-in", fill: "forwards" },
    ).finished;
    onClose();
  }
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? "wide" : ""} ${className}`}
      aria-labelledby="modal-title"
      aria-describedby="modal-description"
      onCancel={(event) => {
        event.preventDefault();
        dismiss();
      }}
      onClick={(event) => {
        if (event.target === ref.current) {
          const box = ref.current.getBoundingClientRect();
          if (
            event.clientX < box.left ||
            event.clientX > box.right ||
            event.clientY < box.top ||
            event.clientY > box.bottom
          )
            dismiss();
        }
      }}
    >
      <button
        className="icon-button modal-close"
        aria-label="关闭弹窗"
        disabled={!onClose}
        onClick={dismiss}
      >
        <X size={18} />
      </button>
      <div className="modal-heading">
        <h2 id="modal-title">{title}</h2>
        <p id="modal-description">{description}</p>
      </div>
      <div className="modal-body">{children}</div>
      {footer && <div className="modal-footer">{footer}</div>}
    </dialog>
  );
}
