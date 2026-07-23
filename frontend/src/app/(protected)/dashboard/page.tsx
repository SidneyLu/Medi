"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { StreamingChatPanel } from "@/components/streaming-chat-panel";
import { api } from "@/lib/api/client";

const SEX_LABEL = { female: "女性", male: "男性", other: "其他", unknown: "未说明" } as const;

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.getProfile });
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.listConversations });
  const [activeId, setActiveId] = useState("");
  const [useProfile, setUseProfile] = useState(true);
  const [useMemory, setUseMemory] = useState(true);
  const userProfile = profile.data?.profile;

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

  function refreshConversation() {
    if (!resolvedActiveId) return;
    queryClient.invalidateQueries({ queryKey: ["conversation", resolvedActiveId] });
    queryClient.invalidateQueries({ queryKey: ["conversations"] });
  }

  return (
    <div className="page home">
      <div className="page-heading compact">
        <div>
          <h1>{userProfile?.nickname ? `你好，${userProfile.nickname}` : "健康主页"}</h1>
          <p>查看画像，直接开始健康咨询</p>
        </div>
      </div>

      <div className="home-layout">
        <aside className="panel home-profile">
          <header className="panel-head">
            <div>
              <h2>健康画像</h2>
              <p>问答时可选用这些信息</p>
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

        <section className="panel home-chat streaming-panel">
          <header className="panel-head">
            <div>
              <h2>健康咨询</h2>
              <p>仅提供科普参考，不替代诊疗</p>
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              {!resolvedActiveId && (
                <button className="text-button" type="button" onClick={() => create.mutate()} disabled={create.isPending}>
                  {create.isPending ? "创建中…" : "新建咨询"}
                </button>
              )}
              <Link className="text-button" href="/chat">全部记录</Link>
            </div>
          </header>
          {resolvedActiveId ? (
            <StreamingChatPanel
              key={resolvedActiveId}
              conversationId={resolvedActiveId}
              initialMessages={detail.data?.messages ?? []}
              useProfile={useProfile}
              useMemory={useMemory}
              onUseProfileChange={setUseProfile}
              onUseMemoryChange={setUseMemory}
              hasProfile={Boolean(userProfile)}
              profileTags={profile.data?.tags ?? []}
              compact
              placeholder="输入你的健康问题…"
              onFinished={refreshConversation}
            />
          ) : (
            <div className="empty compact" style={{ padding: 24 }}>
              <p>新建一次咨询后即可开始流式问答</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
