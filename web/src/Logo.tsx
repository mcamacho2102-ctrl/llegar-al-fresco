/** Símbolo de Llegar al fresco: un banco de parque a la sombra de un árbol. */
export function LogoMark({ size = 44 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <rect width="64" height="64" rx="16" fill="#0E5242" />
      <circle cx="22" cy="23" r="11.5" fill="#9AD8BC" />
      <circle cx="34" cy="18.5" r="9.5" fill="#9AD8BC" />
      <circle cx="43" cy="24.5" r="7" fill="#9AD8BC" />
      <path d="M22 31v20" stroke="#9AD8BC" strokeWidth="3.8" strokeLinecap="round" />
      <g fill="none" stroke="#FFFFFF" strokeWidth="3.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M29 42.5h19" />
        <path d="M48 42.5l3.2-10.5" />
        <path d="M32 42.5v8.5M45 42.5v8.5" />
      </g>
    </svg>
  );
}

export default function Logo({ subtitle = "Madrid a pie, con sitios para sentarte" }: { subtitle?: string }) {
  return (
    <>
      <LogoMark />
      <span>
        <span className="brand-name">Llegar al fresco</span>
        <small>{subtitle}</small>
      </span>
    </>
  );
}
