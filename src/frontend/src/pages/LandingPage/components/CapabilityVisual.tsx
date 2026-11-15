import { useRef } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@/components/common/genericIconComponent";
import { cn } from "@/utils/utils";
import { usePipelinePlayback } from "../hooks/use-landing-motion";
import GlassSurface from "./GlassSurface";
import PipelineConnector from "./PipelineConnector";
import "./capability-visual.css";

const pipelines = {
  canvas: [
    {
      icon: "MessageSquare",
      label: "landing.inputTitle",
      caption: "landing.canvasStep1",
    },
    {
      icon: "Sparkles",
      label: "landing.modelTitle",
      caption: "landing.canvasStep2",
    },
    {
      icon: "Text",
      label: "landing.outputTitle",
      caption: "landing.canvasStep3",
    },
  ],
  knowledge: [
    {
      icon: "Files",
      label: "landing.documents",
      caption: "landing.knowledgeStep1",
    },
    {
      icon: "Search",
      label: "landing.retrieval",
      caption: "landing.knowledgeStep2",
    },
    {
      icon: "BrainCircuit",
      label: "landing.context",
      caption: "landing.knowledgeStep3",
    },
  ],
  integration: [
    {
      icon: "Workflow",
      label: "landing.workflowNav",
      caption: "landing.integrationStep1",
    },
    {
      icon: "Braces",
      label: "landing.endpoint",
      caption: "landing.integrationStep2",
    },
    {
      icon: "AppWindow",
      label: "landing.application",
      caption: "landing.integrationStep3",
    },
  ],
} as const;

export default function CapabilityVisual({
  variant,
  title,
  description,
  index,
}: {
  variant: keyof typeof pipelines;
  title: string;
  description: string;
  index: number;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLElement>(null);
  const { stage, motion } = usePipelinePlayback(ref);
  const nodes = pipelines[variant];

  return (
    <article
      ref={ref}
      className="landing-capability"
      data-reveal
      data-motion={motion}
      data-stage={stage}
    >
      <GlassSurface className="landing-capability-surface">
        <div className="landing-card-copy">
          <span className="landing-card-number" aria-hidden="true">
            0{index + 1}
          </span>
          <h3>{t(title)}</h3>
          <p>{t(description)}</p>
        </div>
        <div
          className={cn("landing-card-art", `landing-card-art-${variant}`)}
          aria-hidden="true"
        >
          <div className="landing-mini-pipeline">
            {nodes.map((node, nodeIndex) => (
              <div
                key={node.label}
                className="landing-mini-step"
                data-active={stage === nodeIndex}
                data-complete={stage > nodeIndex}
              >
                <div className="landing-mini-node">
                  <Icon name={node.icon} />
                  <span>{t(node.label)}</span>
                  <i />
                </div>
                {nodeIndex < nodes.length - 1 && (
                  <PipelineConnector
                    active={stage >= nodeIndex}
                    className="landing-mini-connector"
                  />
                )}
              </div>
            ))}
          </div>
          <div className="landing-mini-progress">
            {nodes.map((node, nodeIndex) => (
              <span key={node.label} data-active={stage >= nodeIndex} />
            ))}
          </div>
        </div>
        <p className="landing-capability-caption">
          <span className="landing-caption-dot" aria-hidden="true" />
          {t(nodes[Math.min(stage, 2)].caption)}
        </p>
      </GlassSurface>
      {index < 2 && <PipelineConnector className="landing-capability-bridge" />}
    </article>
  );
}
