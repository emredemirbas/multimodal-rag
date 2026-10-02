"use client";

import { useFormStatus } from "react-dom";

interface SubmitButtonProps {
  children: React.ReactNode;
  pendingLabel: string;
  className?: string;
  disabled?: boolean;
}

export function SubmitButton({
  children,
  pendingLabel,
  className = "button button--primary",
  disabled = false,
}: SubmitButtonProps) {
  const { pending } = useFormStatus();
  const isDisabled = disabled || pending;

  return (
    <button
      type="submit"
      className={className}
      disabled={isDisabled}
      aria-disabled={isDisabled}
    >
      {pending ? pendingLabel : children}
    </button>
  );
}
