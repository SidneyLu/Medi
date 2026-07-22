"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FileText, Plus, Send } from "lucide-react";
import { api } from "@/lib/api/client";
import type { ConversationDetail } from "@/lib/api/types";

function MessageBubble({ message }: { message: ConversationDetail["messages"][number] }) {
  const isUser = message.role === "user";
  return (
    <article className={`message ${isUser ? "user" : "assistant"}`}>
      <div className="message-meta">
        {isUser ? "你的问题" : "循证健康信息"}
        {message.risk_level === "high" && <span className="tag danger">紧急提示</span>}
      </div>
      {message.risk_level === "high" && (
        <div className="notice urgent" style={{ marginBottom: 12 }}>
          <AlertTriangle size={17} />
          <span>该提示不能替代紧急服务，如存在危险，请立即联系当地急救服务或前往急诊</span>
        </div>
      )}
      <p>{message.content}</p>
      {!isUser && message.evidence_available === false && (
        <div className="notice" style={{ marginTop: 12 }}>当前未检索到足以支撑该问题的可靠来源，因此不提供医学解释</div>
      )}
      {message.suggestions && (
        <div style={{ marginTop: 14 }}>
          <b style={{ fontSize: 13 }}>可考虑准备的信息</b>
          <ul style={{ margin: "7px 0 0", paddingLeft: 19, fontSize: 13 }}>
            {message.suggestions.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      )}
      {message.profile_tags_used && message.profile_tags_used.length > 0 && (
        <div className="tag-row" style={{ marginTop: 13 }}>
          <span className="tag">已结合健康画像</span>
          {message.profile_tags_used.map((tag) => <span className="tag neutral" key={tag}>{tag}</span>)}
        </div>
      )}
      {message.citations && message.citations.length > 0 && (
        <div className="citation-list">
          {message.citations.map((citation) => (
            <div className="citation citation-static" key={citation.chunk_id}>
              <FileText size={15} />
              <span>
                <b>{citation.article_title}</b>
                <br />
                {citation.section_title}
              </span>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

export default function ChatPage() {
  const queryClient = useQueryClient();
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.getProfile });
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.listConversations });
  const [activeId, setActiveId] = useState<string>("chat-demo");
  const [question, setQuestion] = useState("");
  const [useProfile, setUseProfile] = useState(true);
  const [useMemory, setUseMemory] = useState(true);
  const hasProfile = Boolean(profile.data?.profile);
  const resolvedActiveId = conversations.data?.items.some((item) => item.conversation_id === activeId)
    ? activeId
    : conversations.data?.items[0]?.conversation_id ?? "";
  const detail = useQuery({
    queryKey: ["conversation", resolvedActiveId],
    queryFn: () => api.getConversation(resolvedActiveId),
    enabled: Boolean(resolvedActiveId),
  });
  const create = useMutation({
    mutationFn: api.createConversation,
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      setActiveId(conversation.conversation_id);
    },
  });
  const send = useMutation({
    mutationFn: () => api.sendMessage(resolvedActiveId, question, useProfile, useMemory),
    onSuccess: () => {
      setQuestion("");
      queryClient.invalidateQueries({ queryKey: ["conversation", resolvedActiveId] });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (question.trim() && resolvedActiveId) send.mutate();
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">大模型循证问答</p>
          <h1>健康咨询</h1>
          <p>回答仅基于已检索到的授权知识内容，并标注信息来源</p>
        </div>
      </div>
      <div className="chat-layout">
        <aside className="panel conversation-sidebar">
          <header className="panel-head">
            <div>
              <h2>咨询记录</h2>
            </div>
            <button title="新建咨询" aria-label="新建咨询" className="icon-button" onClick={() => create.mutate()}>
              <Plus size={19} />
            </button>
          </header>
          <div className="conversation-list">
            {conversations.data?.items.map((conversation) => (
              <button
                key={conversation.conversation_id}
                className={`conversation-item ${conversation.conversation_id === resolvedActiveId ? "active" : ""}`}
                onClick={() => setActiveId(conversation.conversation_id)}
              >
                <strong>{conversation.title}</strong>
                <small>{conversation.preview || "等待输入问题"}</small>
              </button>
            ))}
          </div>
        </aside>
        <section className="panel chat-panel">
          {detail.isLoading ? (
            <div className="loading"><div className="spinner" /></div>
          ) : (
            <>
              <div className="message-stream">
                {detail.data?.messages.length ? (
                  detail.data.messages.map((message) => (
                    <MessageBubble key={message.message_id} message={message} />
                  ))
                ) : (
                  <div className="empty">
                    <p>描述你的健康问题，请勿将这里的内容作为诊断或紧急医疗服务</p>
                  </div>
                )}
                {send.isPending && (
                  <article className="message assistant">
                    <div className="message-meta">正在检索医学来源</div>
                    <div className="spinner" />
                  </article>
                )}
              </div>
              <form className="chat-composer" onSubmit={submit}>
                <div className="composer-toggles">
                  <label className="checkbox composer-profile">
                    <input type="checkbox" checked={useProfile} onChange={(event) => setUseProfile(event.target.checked)} />
                    使用我的健康画像
                  </label>
                  <label className="checkbox composer-profile">
                    <input type="checkbox" checked={useMemory} onChange={(event) => setUseMemory(event.target.checked)} />
                    使用多轮会话记忆
                  </label>
                </div>
                {useProfile && !hasProfile && (
                  <p className="composer-hint">
                    尚未填写健康画像，请先完善 <Link href="/profile">我的画像</Link>，否则无法个性化
                  </p>
                )}
                {useProfile && hasProfile && profile.data?.tags?.length ? (
                  <div className="tag-row composer-tags">
                    {profile.data.tags.slice(0, 8).map((tag) => (
                      <span className="tag neutral" key={tag}>{tag}</span>
                    ))}
                  </div>
                ) : null}
                <div className="composer-row">
                  <textarea
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.nativeEvent.isComposing) return;
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                    placeholder="例如：最近经常头晕，持续约两周，起身时更明显…"
                    aria-label="输入健康问题"
                  />
                  <button
                    className="primary-button composer-send"
                    disabled={!question.trim() || send.isPending || !resolvedActiveId}
                  >
                    {send.isPending ? "生成中…" : "发送"}
                    <Send size={16} />
                  </button>
                </div>
              </form>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
