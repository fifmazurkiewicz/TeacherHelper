import { useId, useState } from "react";

type Props = {
  /** Puste = tylko pole (np. tabela); ustaw **ariaLabel**. */
  label?: string;
  /** Gdy brak `label` — wymagane do dostępności. */
  ariaLabel?: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  minLength?: number;
  autoComplete?: string;
  /** Dodatkowe klasy na `input` (np. mniejsza czcionka w adminie). */
  inputClassName?: string;
  /** Otoczka ikony „oko” (szerokość w tabeli admina itd.). */
  fieldWrapperClassName?: string;
  /** Mniejsze ikony / pole (wiersz tabeli). */
  compact?: boolean;
  placeholder?: string;
};

function IconEye({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"
      />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

function IconEyeSlash({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88"
      />
    </svg>
  );
}

export function PasswordField({
  label,
  ariaLabel = "Hasło",
  value,
  onChange,
  required,
  minLength,
  autoComplete,
  inputClassName = "",
  fieldWrapperClassName = "",
  compact = false,
  placeholder,
}: Props) {
  const id = useId();
  const [show, setShow] = useState(false);
  const baseInput = [
    "w-full min-w-0 rounded-md border border-ink-800/20 bg-paper-50 pl-3 dark:border-paper-100/20 dark:bg-ink-950",
    compact ? "py-1.5 pr-9 text-xs" : "py-2 pr-11",
    inputClassName,
  ]
    .filter(Boolean)
    .join(" ");
  const wrap = label ? "flex flex-col gap-1 text-sm" : "min-w-0 flex-1";

  const iconSz = compact ? "h-4 w-4" : "h-5 w-5";
  const btnPad = compact ? "p-1" : "p-1.5";

  return (
    <div className={wrap}>
      {label ? <label htmlFor={id}>{label}</label> : null}
      <div className={`relative ${fieldWrapperClassName}`.trimEnd()}>
        <input
          id={id}
          type={show ? "text" : "password"}
          required={required}
          minLength={minLength}
          value={value}
          autoComplete={autoComplete}
          placeholder={placeholder}
          aria-label={label ? undefined : ariaLabel}
          onChange={(e) => onChange(e.target.value)}
          className={baseInput}
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className={
            "absolute right-1 top-1/2 -translate-y-1/2 rounded text-ink-600 hover:bg-ink-800/10 dark:text-paper-400 dark:hover:bg-paper-100/10 " +
            btnPad
          }
          aria-label={show ? "Ukryj hasło" : "Pokaż hasło"}
          aria-pressed={show}
        >
          {show ? <IconEyeSlash className={iconSz} /> : <IconEye className={iconSz} />}
        </button>
      </div>
    </div>
  );
}
