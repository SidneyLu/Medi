"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ConversationSidebar, StreamingChatPanel } from "@/components/streaming-chat-panel";
import { api } from "@/lib/api/client";

export default function ChatPage() {
  const queryClient = useQueryClient();
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.getProfile });
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.listConversations });
  const [activeId, setActiveId] = useState<string>("chat-demo");
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

  function refreshConversation() {
    queryClient.invalidateQueries({ queryKey: ["conversation", resolvedActiveId] });
    queryClient.invalidateQueries({ queryKey: ["conversations"] });
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">大模型循证问答</p>
          <h1>健康咨询</h1>
          <p>回答基于本地授权知识检索生成，并在正文中附主题页行内引用</p>
        </div>
      </div>
      <div className="chat-layout">
        <ConversationSidebar
          items={conversations.data?.items ?? []}
          activeId={resolvedActiveId}
          onSelect={setActiveId}
          onCreate={() => create.mutate()}
          creating={create.isPending}
        />
        <section className="panel chat-panel streaming-panel">
          {detail.isLoading ? (
            <div className="loading">
              <div className="spinner" />
            </div>
          ) : resolvedActiveId ? (
            <StreamingChatPanel
              key={resolvedActiveId}
              conversationId={resolvedActiveId}
              initialMessages={detail.data?.messages ?? []}
              useProfile={useProfile}
              useMemory={useMemory}
              onUseProfileChange={setUseProfile}
              onUseMemoryChange={setUseMemory}
              hasProfile={hasProfile}
              profileTags={profile.data?.tags ?? []}
              onFinished={refreshConversation}
            />
          ) : (
            <div className="empty">
              <p>请先新建一次健康咨询</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
