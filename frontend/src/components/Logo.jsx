import { Link } from "react-router-dom";

export const Logo = ({ to = "/", light = false }) => (
  <Link to={to} className="flex items-center gap-2 group" data-testid="brand-logo">
    <span className="relative flex h-7 w-7 items-center justify-center">
      <svg viewBox="0 0 28 28" className="h-7 w-7" fill="none">
        <path d="M14 3C8 3 4 8 4 14c0 6 5 11 10 11 2.5-6 6-8 9-9-4-1-7 1-9 4 1-6 5-10 10-11-3-4-7-6-10-6z"
              fill={light ? "#ffffff" : "#202020"} />
        <circle cx="19" cy="8" r="2.4" fill="#ff682c" />
      </svg>
    </span>
    <span className={`font-display text-[19px] tracking-tight ${light ? "text-white" : "text-graphite"}`}>
      Green Papaya
    </span>
  </Link>
);
