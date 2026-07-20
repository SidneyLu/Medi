"use client";

import { useRouter } from "next/navigation";

type ReportStepsProps = {
  step: 1 | 2 | 3;
  reportId?: string;
};

const LABELS = ["上传报告", "核对识别结果", "查看解读"] as const;

export function ReportSteps({ step, reportId }: ReportStepsProps) {
  const router = useRouter();

  function hrefFor(target: 1 | 2 | 3): string | null {
    if (target === 1) return "/reports";
    if (!reportId) return null;
    if (target === 2) return `/reports/${reportId}/ocr`;
    return `/reports/${reportId}/result`;
  }

  function onStepClick(target: 1 | 2 | 3) {
    // Only allow jumping back to earlier steps; ignore current and future steps.
    if (target >= step) return;
    const href = hrefFor(target);
    if (!href) return;
    router.push(href);
  }

  return (
    <div className="stepper" aria-label="报告处理进度">
      {LABELS.map((label, index) => {
        const target = (index + 1) as 1 | 2 | 3;
        const active = step >= target;
        const clickable = target < step && hrefFor(target) !== null;

        return (
          <div style={{ display: "contents" }} key={label}>
            <button
              type="button"
              className={`step ${active ? "active" : ""} ${clickable ? "clickable" : ""}`}
              onClick={() => onStepClick(target)}
              disabled={!clickable}
              aria-current={step === target ? "step" : undefined}
              title={clickable ? `返回：${label}` : undefined}
            >
              <b>{target}</b>
              <span>{label}</span>
            </button>
            {index < 2 && <div className="step-line" />}
          </div>
        );
      })}
    </div>
  );
}
