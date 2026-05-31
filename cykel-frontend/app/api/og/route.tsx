import { ImageResponse } from "next/og";
import { NextRequest } from "next/server";

export const runtime = "edge";

const CATEGORY_LABELS: Record<string, string> = {
  resultater: "RESULTATER",
  startliste: "STARTLISTE",
  transfer: "TRANSFER",
  profil: "PROFIL",
  analyse: "ANALYSE",
  generelt: "NYHEDER",
  race_report: "LØBSRAPPORT",
  interview: "INTERVIEW",
  general: "NYHEDER",
  analysis: "ANALYSE",
};

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const title = searchParams.get("title") ?? "Klassementet";
  const photo = searchParams.get("photo") ?? null;
  const category = searchParams.get("category") ?? "generelt";
  const categoryLabel = CATEGORY_LABELS[category] ?? "NYHEDER";

  return new ImageResponse(
    (
      <div
        style={{
          width: "1200px",
          height: "630px",
          display: "flex",
          position: "relative",
          background: "#020617",
          overflow: "hidden",
        }}
      >
        {/* Background photo */}
        {photo && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={photo}
            alt=""
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: "top center",
              opacity: 0.45,
            }}
          />
        )}

        {/* Gradient overlay — dark at bottom, lighter at top */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: photo
              ? "linear-gradient(to bottom, rgba(2,6,23,0.2) 0%, rgba(2,6,23,0.5) 40%, rgba(2,6,23,0.92) 75%, rgba(2,6,23,1) 100%)"
              : "linear-gradient(135deg, #0f172a 0%, #020617 100%)",
          }}
        />

        {/* Emerald accent line at top */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "4px",
            background: "#10b981",
          }}
        />

        {/* Content */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            justifyContent: "flex-end",
            padding: "52px 60px",
          }}
        >
          {/* Category badge */}
          <div
            style={{
              display: "flex",
              marginBottom: "20px",
            }}
          >
            <span
              style={{
                fontSize: "13px",
                letterSpacing: "0.2em",
                color: "#10b981",
                fontWeight: 600,
                textTransform: "uppercase",
                fontFamily: "sans-serif",
              }}
            >
              {categoryLabel}
            </span>
          </div>

          {/* Title */}
          <div
            style={{
              fontSize: title.length > 60 ? "46px" : title.length > 40 ? "54px" : "62px",
              fontWeight: 800,
              color: "#ffffff",
              lineHeight: 1.1,
              letterSpacing: "-0.01em",
              fontFamily: "sans-serif",
              marginBottom: "32px",
              maxWidth: "960px",
            }}
          >
            {title}
          </div>

          {/* Footer: logo + domain */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
            }}
          >
            {/* K logo */}
            <div
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "8px",
                background: "#10b981",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "18px",
                fontWeight: 900,
                color: "#000",
                fontFamily: "sans-serif",
              }}
            >
              K
            </div>
            <span
              style={{
                fontSize: "15px",
                color: "#475569",
                fontFamily: "sans-serif",
                letterSpacing: "0.05em",
              }}
            >
              klassementet.dk
            </span>
          </div>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
    }
  );
}
