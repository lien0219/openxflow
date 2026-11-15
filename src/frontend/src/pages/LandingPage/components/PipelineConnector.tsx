import { cn } from "@/utils/utils";
import "./pipeline-connector.css";

const streamPoints = Array.from({ length: 45 }, (_, index) => {
  const column = index % 15;
  const row = Math.floor(index / 15);
  const x = 8 + column * 6;
  return {
    x,
    y: 20 + Math.sin((column / 14) * Math.PI * 2) * (row - 1) * 6,
    opacity: 0.12 + Math.sin((column / 14) * Math.PI) * 0.24,
  };
});

export default function PipelineConnector({
  active = true,
  className = "",
}: {
  active?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn("landing-pipeline-connector", className)}
      data-active={active}
      aria-hidden="true"
    >
      <svg viewBox="0 0 100 40" preserveAspectRatio="none" focusable="false">
        <g fill="currentColor">
          {streamPoints.map((point, index) => (
            <circle
              key={index}
              cx={point.x}
              cy={point.y}
              r="0.7"
              opacity={point.opacity}
            />
          ))}
        </g>
        <path className="landing-pipeline-track" d="M0 20 H100" />
        <path className="landing-pipeline-halo" d="M0 20 H100" />
        <path className="landing-pipeline-current" d="M0 20 H100" />
      </svg>
      <i className="landing-pipeline-port" />
      <i className="landing-pipeline-port landing-pipeline-port-end" />
    </span>
  );
}
