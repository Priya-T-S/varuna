import type { SVGProps } from "react";

/** Small stroke icon set (Lucide-style geometry), inlined to avoid a dependency. */
type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 16, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    ...props,
  };
}

export const IconHome = (p: IconProps) => (
  <svg {...base(p)}><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /><path d="M10 21v-6h4v6" /></svg>
);
export const IconBell = (p: IconProps) => (
  <svg {...base(p)}><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" /></svg>
);
export const IconSparkles = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z" /><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" /></svg>
);
export const IconTarget = (p: IconProps) => (
  <svg {...base(p)}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>
);
export const IconBrain = (p: IconProps) => (
  <svg {...base(p)}><path d="M9 4a3 3 0 0 0-3 3v.2A3 3 0 0 0 4 10a3 3 0 0 0 1 2.3A3 3 0 0 0 6 18a3 3 0 0 0 3 2h0a3 3 0 0 0 3-3V7a3 3 0 0 0-3-3z" /><path d="M15 4a3 3 0 0 1 3 3v.2A3 3 0 0 1 20 10a3 3 0 0 1-1 2.3A3 3 0 0 1 18 18a3 3 0 0 1-3 2h0a3 3 0 0 1-3-3" /></svg>
);
export const IconHistory = (p: IconProps) => (
  <svg {...base(p)}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /><path d="M12 7v5l3 2" /></svg>
);
export const IconActivity = (p: IconProps) => (
  <svg {...base(p)}><path d="M3 12h4l3-8 4 16 3-8h4" /></svg>
);
export const IconDrop = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 3c-4 5-7 8.6-7 12.2A7 7 0 0 0 19 15.2C19 11.6 16 8 12 3z" /></svg>
);
export const IconSend = (p: IconProps) => (
  <svg {...base(p)}><path d="M5 12 3 4l18 8-18 8z" /><path d="M5 12h8" /></svg>
);
export const IconSettings = (p: IconProps) => (
  <svg {...base(p)}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>
);
export const IconMapPin = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></svg>
);
export const IconArrowRight = (p: IconProps) => (
  <svg {...base(p)}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
export const IconCheck = (p: IconProps) => (
  <svg {...base(p)}><path d="M4 12.5 9 17.5 20 6.5" /></svg>
);
export const IconX = (p: IconProps) => (
  <svg {...base(p)}><path d="M6 6l12 12M18 6 6 18" /></svg>
);
export const IconAlertTriangle = (p: IconProps) => (
  <svg {...base(p)}><path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></svg>
);
export const IconUsers = (p: IconProps) => (
  <svg {...base(p)}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.3a3.5 3.5 0 0 1 0 7.4M21.5 20a6.5 6.5 0 0 0-4-6" /></svg>
);
export const IconCpu = (p: IconProps) => (
  <svg {...base(p)}><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" /></svg>
);
export const IconUpload = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></svg>
);
export const IconMenu = (p: IconProps) => (
  <svg {...base(p)}><path d="M4 7h16M4 12h16M4 17h16" /></svg>
);
export const IconPlay = (p: IconProps) => (
  <svg {...base(p)}><path d="M7 4.5v15l12.5-7.5z" /></svg>
);
export const IconBook = (p: IconProps) => (
  <svg {...base(p)}><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" /><path d="M4 19V5M8 7h7" /></svg>
);

/** The VARUNA mark: a raindrop in the brand tile. */
export function LogoMark({ size = 30 }: { size?: number }) {
  return (
    <svg aria-hidden height={size} viewBox="0 0 32 32" width={size}>
      <defs>
        <linearGradient id="varuna-g" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#2a7797" />
          <stop offset="1" stopColor="#10303f" />
        </linearGradient>
      </defs>
      <rect fill="url(#varuna-g)" height="32" rx="8" width="32" />
      <path d="M16 6c-4 5.2-7 9-7 12.6A7 7 0 0 0 23 18.6C23 15 20 11.2 16 6z" fill="#d7e9f0" />
      <path d="M12.6 19.2a3.4 3.4 0 0 0 3.4 3.3" fill="none" stroke="#2a7797" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  );
}
