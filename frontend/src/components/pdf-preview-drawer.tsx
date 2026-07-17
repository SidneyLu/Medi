"use client";
/* eslint-disable @next/next/no-img-element */

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, FileText, Minus, Plus, X } from "lucide-react";
import { api } from "@/lib/api/client";

export function PdfPreviewDrawer({ chunkId, onClose }: { chunkId: string; onClose: () => void }) {
  const citation = useQuery({ queryKey: ["citation", chunkId], queryFn: () => api.getCitation(chunkId) });
  const [page, setPage] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);
  useEffect(() => { const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); }; window.addEventListener("keydown", close); return () => window.removeEventListener("keydown", close); }, [onClose]);
  const currentPage = page ?? citation.data?.page_start ?? null;
  const imageUrl = citation.data && currentPage ? api.previewUrl(citation.data.document_id, currentPage) : "";
  const boxes = useMemo(() => citation.data?.source_bboxes.filter((box) => box.page === currentPage) ?? [], [citation.data, currentPage]);
  return <div className="pdf-overlay" role="dialog" aria-modal="true" aria-label="PDF 原页预览"><aside className="pdf-drawer"><header className="pdf-head"><div><p className="eyebrow">PDF 原页核验</p><h2>{citation.data?.document_title ?? "正在加载来源"}</h2></div><button className="icon-button" onClick={onClose} aria-label="关闭预览"><X size={20} /></button></header>{citation.isLoading && <div className="loading"><div className="spinner" /></div>}{citation.isError && <div className="pdf-error"><FileText size={28} /><b>无法加载页面预览</b><p>可根据引用页码和原文片段核验来源。</p></div>}{citation.data && currentPage && <><div className="pdf-toolbar"><button className="icon-button" title="缩小" onClick={() => setZoom((value) => Math.max(.65, value - .15))}><Minus size={17} /></button><span>{Math.round(zoom * 100)}%</span><button className="icon-button" title="放大" onClick={() => setZoom((value) => Math.min(2.2, value + .15))}><Plus size={17} /></button><span className="pdf-page-count">第 {currentPage} / {citation.data.page_count} 页</span></div><div className="pdf-canvas"><div className="pdf-image-wrap" style={{ transform: `scale(${zoom})` }}><img src={imageUrl} alt={`${citation.data.document_title} 第 ${currentPage} 页`} onError={(event) => { event.currentTarget.style.display = "none"; }} />{boxes.map((box, index) => <span className="pdf-highlight" key={index} style={{ left: `${box.bbox[0]}%`, top: `${box.bbox[1]}%`, width: `${box.bbox[2] - box.bbox[0]}%`, height: `${box.bbox[3] - box.bbox[1]}%` }} />)}</div></div><div className="pdf-nav"><button className="secondary-button" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={16} />上一页</button><button className="secondary-button" disabled={currentPage >= citation.data.page_count} onClick={() => setPage(currentPage + 1)}>下一页<ChevronRight size={16} /></button></div><div className="pdf-excerpt"><b>{citation.data.section_title}</b><p>{citation.data.source_excerpt}</p><small>文档版本 {citation.data.document_version} · 高亮区域为解析器提供的原文定位。</small></div></>}</aside></div>;
}
