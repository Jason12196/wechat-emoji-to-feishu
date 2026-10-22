export default function Sticker({ item, large = false }) {
  const { kind, label } = item;
  if (item.url)
    return (
      <img
        className={`sticker-art real-sticker ${large ? "large" : ""}`}
        src={item.url}
        alt={label}
        loading="lazy"
        draggable="false"
      />
    );
  const palette = [
    { face: "#23c8ff", ink: "#075d9b", ear: "#08a8ed", blush: "#ff748f" },
    { face: "#ffcb26", ink: "#9a4f12", ear: "#ffa61e", blush: "#ff7356" },
    { face: "#ff76b8", ink: "#a42871", ear: "#e84c9c", blush: "#ffb5d5" },
    { face: "#ff9751", ink: "#953b21", ear: "#ff6c37", blush: "#ffcf5e" },
    { face: "#a77aff", ink: "#5425a0", ear: "#8149ee", blush: "#ff8ebb" },
    { face: "#5ce39b", ink: "#166c4a", ear: "#27c879", blush: "#ff8d76" },
  ][kind];
  return (
    <svg
      className={`sticker-art ${large ? "large" : ""}`}
      viewBox="0 0 160 145"
      role="img"
      aria-label={`${label}演示表情`}
    >
      <g
        stroke={palette.ink}
        strokeWidth="3.5"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {kind === 0 && (
          <>
            <path
              d="M44 45 34 19 62 29Q81 22 99 29l27-10-9 29q17 48-35 51Q28 101 44 45Z"
              fill={palette.face}
            />
            <path d="m58 55 9 6-9 6m43-12-9 6 9 6M71 77q10 9 20 0" />
            <path d="m24 74-9 4m120-6 10 6" />
          </>
        )}
        {kind === 1 && (
          <>
            <path
              d="M39 61q0-38 41-38t41 38v22q-1 19-40 19-40 0-42-19Z"
              fill={palette.face}
            />
            <path d="m59 54 9-2m25 0 9 2M61 67h1m36 0h1M71 83h18" />
            <path d="m34 81-12 7m104-8 12 9" />
          </>
        )}
        {kind === 2 && (
          <>
            <path
              d="M44 43Q27 7 52 17l16 19m31 0 12-19q25-9 9 29"
              fill={palette.ear}
            />
            <ellipse cx="81" cy="66" rx="43" ry="34" fill={palette.face} />
            <path d="M64 62v4m34-4v4m-26 17q10-13 20 0M124 61l13-9m-5-9 5 9 10-1" />
          </>
        )}
        {kind === 3 && (
          <>
            <path
              d="M44 41q-16-24-24-7-6 15 14 22m87-13q16-24 24-7 6 15-14 22"
              fill={palette.ear}
            />
            <ellipse cx="80" cy="64" rx="47" ry="36" fill={palette.face} />
            <path d="m55 59 10-5m31 0 10 5M63 68h1m34 0h1M68 81q13 12 25-1" />
            <path d="m42 96-14 13m86-13 14 13" />
          </>
        )}
        {kind === 4 && (
          <>
            <path
              d="m45 42 15-9q-2-23 11-18 11 5 14 17h22q23 0 16 17 16 13-1 26-1 22-23 20H61q-25-2-16-20-16-13 0-25Z"
              fill={palette.face}
            />
            <path d="m63 56 7 5-7 5m39-10-7 5 7 5M75 79q8 6 16 0" />
            <path d="m29 31-7-6m12-6-3-9m104 75 9 5" />
          </>
        )}
        {kind === 5 && (
          <>
            <path d="M40 40h78v35q0 24-39 24T40 75Z" fill={palette.face} />
            <path d="M119 48q30-5 26 15-3 14-26 9M58 18q-6-7 0-14m22 14q-6-7 0-14m22 14q-6-7 0-14M62 61v4m34-4v4m-22 15h13" />
            <path d="M30 106h101" />
          </>
        )}
        <g fill={palette.blush} stroke="none">
          <ellipse cx="52" cy="73" rx="5" ry="3" />
          <ellipse cx="110" cy="73" rx="5" ry="3" />
        </g>
      </g>
      <text
        x="80"
        y="132"
        textAnchor="middle"
        fill="currentColor"
        fontSize="19"
        fontWeight="750"
        fontFamily="-apple-system, BlinkMacSystemFont, sans-serif"
      >
        {label}
      </text>
    </svg>
  );
}
