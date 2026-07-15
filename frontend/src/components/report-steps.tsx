export function ReportSteps({ step }: { step: 1 | 2 | 3 }) {
  const labels = ["上传报告", "核对识别结果", "查看解读"];
  return <div className="stepper" aria-label="报告处理进度">{labels.map((label, index) => <div style={{ display: "contents" }} key={label}><div className={`step ${step >= index + 1 ? "active" : ""}`}><b>{index + 1}</b><span>{label}</span></div>{index < 2 && <div className="step-line" />}</div>)}</div>;
}
