import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@/components/common/genericIconComponent";
import { cn } from "@/utils/utils";
import { usePipelinePlayback } from "../hooks/use-landing-motion";
import GlassSurface from "./GlassSurface";
import ParticleWater from "./ParticleWater";
import PipelineConnector from "./PipelineConnector";

export default function WorkflowPreview() {
  const { t } = useTranslation();
  const [scenario, setScenario] = useState<"knowledge" | "writing">(
    "knowledge",
  );
  const ref = useRef<HTMLDivElement>(null);
  const { stage, motion } = usePipelinePlayback(ref, scenario);
  const isKnowledge = scenario === "knowledge";
  const nodes = [
    {
      title: t("landing.inputTitle"),
      icon: "MessageSquare",
      label: t("landing.inputLabel"),
      content: t(
        isKnowledge ? "landing.knowledgeInput" : "landing.writingInput",
      ),
    },
    {
      title: t("landing.modelTitle"),
      icon: "Sparkles",
      label: t(
        isKnowledge ? "landing.knowledgeContext" : "landing.writingContext",
      ),
      content: t("landing.modelDescription"),
    },
    {
      title: t("landing.outputTitle"),
      icon: "Text",
      label: t("landing.outputLabel"),
      content: t(
        isKnowledge ? "landing.knowledgeOutput" : "landing.writingOutput",
      ),
    },
  ];
  return (
    <div
      ref={ref}
      className="landing-preview landing-glass"
      data-testid="landing-preview"
      data-motion={motion}
      data-stage={stage}
    >
      <div className="landing-preview-toolbar">
        <div className="landing-preview-heading">
          <span className="landing-preview-symbol" aria-hidden="true">
            <Icon name="Workflow" />
          </span>
          <h2 id="workflow-title">{t("landing.previewTitle")}</h2>
        </div>
        <div
          role="group"
          aria-label={t("landing.scenarioLabel")}
          className="landing-segmented"
        >
          <button
            type="button"
            aria-pressed={isKnowledge}
            onClick={() => setScenario("knowledge")}
          >
            {t("landing.knowledgeScenario")}
          </button>
          <button
            type="button"
            aria-pressed={!isKnowledge}
            onClick={() => setScenario("writing")}
          >
            {t("landing.writingScenario")}
          </button>
        </div>
      </div>
      <div className="landing-preview-canvas">
        <ParticleWater variant="pipeline" />
        <div className="landing-canvas-glow" aria-hidden="true" />
        <ol
          aria-label={t("landing.workflowNav")}
          className="landing-flow-nodes"
        >
          {nodes.map((node, index) => (
            <li
              key={node.title}
              className="landing-flow-node"
              data-active={stage === index}
              data-complete={stage > index}
            >
              <GlassSurface
                className={cn(
                  "landing-node-surface",
                  index === 1 && "landing-node-model",
                )}
              >
                <div className="landing-node-header">
                  <span className="landing-node-icon">
                    <Icon name={node.icon} aria-hidden="true" />
                  </span>
                  <h3>{node.title}</h3>
                  <span className="landing-node-number" aria-hidden="true">
                    {stage > index ? <Icon name="Check" /> : `0${index + 1}`}
                  </span>
                </div>
                <div className="landing-node-body">
                  <p className="landing-node-label">{node.label}</p>
                  <p>{node.content}</p>
                </div>
                <div className="landing-node-progress" aria-hidden="true" />
              </GlassSurface>
              {index < nodes.length - 1 && (
                <PipelineConnector
                  className="landing-workflow-connector"
                  active={stage >= index}
                />
              )}
            </li>
          ))}
        </ol>
      </div>
      <div className="landing-preview-footer">
        <div className="landing-preview-stages" aria-hidden="true">
          {nodes.map((node, index) => (
            <span key={node.title} data-active={stage >= index}>
              <i />
              {node.title}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
