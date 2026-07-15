"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink, Pencil, Send } from "lucide-react";
import { api } from "@/lib/api/client";
import type { ConversationDetail } from "@/lib/api/types";

const SEX_LABEL = { female: "女性", male: "男性", other: "其他", unknown: "未说明" } as const;

function MessageBubble({ message }: { message: ConversationDetail["messages"][number] }) {
  const isUser = message.role === "user";
  return (
    <article className={`message ${isUser ? "user" : "assistant"}`}>
      <div className="message-meta">
        {isUser ? "你的问题" : "健康咨询回复"}
        {message.risk_level === "high" && <span className="tag danger">紧急提示</span>}
      </div>
      {message.risk_level === "high" && (
        <div className="notice urgent" style={{ marginBottom: 12 }}>
          <AlertTriangle size={17} />
          <span>如存在危险，请立即联系当地急救服务或前往急诊。</span>
        </div>
      )}
      <p>{message.content}</p>
      {message.citations && message.citations.length > 0 && (
        <div className="citation-list">
          {message.citations.map((citation) => (
            <a className="citation" href={citation.source_url} target="_blank" rel="noreferrer" key={citation.chunk_id}>
              <ExternalLink size={15} />
              <span>
                <b>{citation.article_title}</b>
                <br />
                {citation.section_title}
              </span>
            </a>
          ))}
        </div>
      )}
    </article>
  );
}

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.getProfile });
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.listConversations });
  const [activeId, setActiveId] = useState("");
  const [question, setQuestion] = useState("");
  const [useProfile, setUseProfile] = useState(true);
  const userProfile = profile.data?.profile;

  useEffect(() => {
    const firstId = conversations.data?.items[0]?.conversation_id ?? "";
    if (!conversations.data?.items.some((item) => item.conversation_id === activeId)) {
      setActiveId(firstId);
    }
  }, [activeId, conversations.data]);

  const detail = useQuery({
    queryKey: ["conversation", activeId],
    queryFn: () => api.getConversation(activeId),
    enabled: Boolean(activeId),
  });

  const create = useMutation({
    mutationFn: api.createConversation,
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      setActiveId(conversation.conversation_id);
    },
  });

  const send = useMutation({
    mutationFn: () => api.sendMessage(activeId, question, useProfile),
    onSuccess: () => {
      setQuestion("");
      queryClient.invalidateQueries({ queryKey: ["conversation", activeId] });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    if (!activeId) {
      create.mutate(undefined, {
        onSuccess: (conversation) => {
          void api.sendMessage(conversation.conversation_id, question, useProfile).then(() => {
            setQuestion("");
            setActiveId(conversation.conversation_id);
            queryClient.invalidateQueries({ queryKey: ["conversation", conversation.conversation_id] });
            queryClient.invalidateQueries({ queryKey: ["conversations"] });
          });
        },
      });
      return;
    }
    send.mutate();
  }

  return (
    <div className="page home">
      <div className="page-heading compact">
        <div>
          <h1>{userProfile?.nickname ? `你好，${userProfile.nickname}` : "健康主页"}</h1>
          <p>查看画像，直接开始健康咨询。</p>
        </div>
      </div>

      <div className="home-layout">
        <aside className="panel home-profile">
          <header className="panel-head">
            <div>
              <h2>健康画像</h2>
              <p>问答时可选用这些信息。</p>
            </div>
            <Link className="icon-button" href="/profile" title="编辑画像" aria-label="编辑画像">
              <Pencil size={16} />
            </Link>
          </header>
          <div className="panel-pad">
            {userProfile ? (
              <>
                <div className="profile-summary single">
                  <div className="profile-kv"><span>出生日期</span><strong>{userProfile.birth_date}</strong></div>
                  <div className="profile-kv"><span>性别</span><strong>{SEX_LABEL[userProfile.sex_at_birth]}</strong></div>
                  <div className="profile-kv"><span>慢病/长期情况</span><strong>{userProfile.chronic_conditions.join("、") || "未记录"}</strong></div>
                  <div className="profile-kv"><span>过敏史</span><strong>{userProfile.allergies.join("、") || "未记录"}</strong></div>
                  <div className="profile-kv"><span>常用药</span><strong>{userProfile.current_medications.join("、") || "未记录"}</strong></div>
                </div>
                {profile.data?.tags.length ? (
                  <div className="tag-row" style={{ marginTop: 14 }}>
                    {profile.data.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="empty compact">
                <p>尚未填写健康画像</p>
                <Link className="primary-button" href="/profile" style={{ marginTop: 12 }}>去完善</Link>
              </div>
            )}
          </div>
        </aside>

        <section className="panel home-chat">
          <header className="panel-head">
            <div>
              <h2>健康咨询</h2>
              <p>仅提供科普参考，不替代诊疗。</p>
            </div>
            <Link className="text-button" href="/chat">全部记录</Link>
          </header>
          <div className="message-stream">
            {detail.isLoading && activeId ? (
              <div className="loading compact"><div className="spinner" /></div>
            ) : detail.data?.messages.length ? (
              detail.data.messages.map((message) => <MessageBubble key={message.message_id} message={message} />)
            ) : (
              <div className="empty compact">
                <p>描述你的不适或健康问题，例如：「最近经常头晕，起身时更明显。」</p>
              </div>
            )}
            {(send.isPending || create.isPending) && (
              <article className="message assistant">
                <div className="message-meta">正在整理回复</div>
                <div className="spinner" />
              </article>
            )}
          </div>
          <form className="chat-composer" onSubmit={submit}>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="输入你的健康问题…"
              aria-label="输入健康问题"
            />
            <div className="composer-tools">
              <label className="checkbox">
                <input type="checkbox" checked={useProfile} onChange={(event) => setUseProfile(event.target.checked)} />
                使用健康画像
              </label>
              <button className="primary-button" disabled={!question.trim() || send.isPending || create.isPending}>
                {send.isPending || create.isPending ? "发送中…" : "发送"}
                <Send size={16} />
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
