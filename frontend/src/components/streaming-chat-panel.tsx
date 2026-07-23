"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, type UIMessage } from "ai";
import { AlertTriangle, Plus } from "lucide-react";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from "@/components/ai-elements/prompt-input";
import { getAccessToken } from "@/lib/api/client";
import type { ChatMessage as StoredChatMessage } from "@/lib/api/types";

function messageText(message: UIMessage): string {
  return (message.parts ?? [])
    .filter((part): part is { type: "text"; text: string } => part.type === "text")
    .map((part) => part.text)
    .join("");
}

function toUiMessages(messages: StoredChatMessage[]): UIMessage[] {
  return messages.map((message) => ({
    id: message.message_id,
    role: message.role,
    parts: [{ type: "text", text: message.content }],
  }));
}

type StreamingChatPanelProps = {
  conversationId: string;
  initialMessages?: StoredChatMessage[];
  useProfile: boolean;
  useMemory: boolean;
  onUseProfileChange?: (value: boolean) => void;
  onUseMemoryChange?: (value: boolean) => void;
  hasProfile?: boolean;
  profileTags?: string[];
  placeholder?: string;
  compact?: boolean;
  onFinished?: () => void;
  emptyTitle?: string;
  emptyDescription?: string;
};

export function StreamingChatPanel({
  conversationId,
  initialMessages = [],
  useProfile,
  useMemory,
  onUseProfileChange,
  onUseMemoryChange,
  hasProfile = true,
  profileTags = [],
  placeholder = "例如：最近经常头晕，持续约两周，起身时更明显…",
  compact = false,
  onFinished,
  emptyTitle = "开始健康咨询",
  emptyDescription = "描述你的健康问题。回答仅基于本地授权知识，正文中的链接来自 MSD 主题页引用 enrichment。",
}: StreamingChatPanelProps) {
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: "/api/chat",
        headers: () => {
          const headers: Record<string, string> = {};
          const token = getAccessToken();
          if (token) headers.Authorization = `Bearer ${token}`;
          return headers;
        },
        prepareSendMessagesRequest: ({ messages, body, headers, credentials, api, trigger, messageId }) => ({
          api,
          headers,
          credentials,
          body: {
            ...body,
            messages,
            conversationId,
            useProfile,
            useMemory,
            trigger,
            messageId,
          },
        }),
      }),
    [conversationId, useProfile, useMemory],
  );

  const { messages, setMessages, sendMessage, status, stop, error } = useChat({
    id: conversationId,
    messages: toUiMessages(initialMessages),
    transport,
    onData: (dataPart) => {
      if (dataPart.type !== "data-citation-patch") return;
      const content =
        typeof dataPart.data === "object" &&
        dataPart.data &&
        "content" in dataPart.data &&
        typeof (dataPart.data as { content?: unknown }).content === "string"
          ? (dataPart.data as { content: string }).content
          : null;
      if (!content) return;
      setMessages((current) => {
        if (!current.length) return current;
        const last = current[current.length - 1];
        if (last.role !== "assistant") return current;
        return [...current.slice(0, -1), { ...last, parts: [{ type: "text", text: content }] }];
      });
    },
    onFinish: () => {
      onFinished?.();
    },
  });

  const seedKey = `${conversationId}:${initialMessages.map((item) => item.message_id).join(",")}`;
  const [seededKey, setSeededKey] = useState(seedKey);
  if (seedKey !== seededKey && status !== "streaming" && status !== "submitted") {
    setSeededKey(seedKey);
    setMessages(toUiMessages(initialMessages));
  }

  const busy = status === "submitted" || status === "streaming";

  return (
    <div className={`streaming-chat ${compact ? "compact" : ""}`}>
      <Conversation className="streaming-chat-thread">
        <ConversationContent>
          {messages.length === 0 ? (
            <ConversationEmptyState title={emptyTitle} description={emptyDescription} />
          ) : (
            messages.map((message) => {
              const text = messageText(message);
              const isUser = message.role === "user";
              const highRisk = !isUser && /急救|急诊|紧急/.test(text);
              return (
                <Message
                  key={message.id}
                  from={message.role}
                  className={isUser ? "medi-msg-user" : "medi-msg-assistant"}
                >
                  <div className="message-meta">
                    {isUser ? "你的问题" : "循证健康信息"}
                    {highRisk ? <span className="tag danger">紧急提示</span> : null}
                  </div>
                  {highRisk ? (
                    <div className="notice urgent" style={{ marginBottom: 12 }}>
                      <AlertTriangle size={17} />
                      <span>该提示不能替代紧急服务，如存在危险，请立即联系当地急救服务或前往急诊</span>
                    </div>
                  ) : null}
                  <MessageContent className="medi-msg-content">
                    {isUser ? (
                      <p className="whitespace-pre-wrap">{text}</p>
                    ) : (
                      <MessageResponse>{text}</MessageResponse>
                    )}
                  </MessageContent>
                </Message>
              );
            })
          )}
          {busy && messages.at(-1)?.role === "user" ? (
            <Message from="assistant" className="medi-msg-assistant">
              <div className="message-meta">正在检索并生成</div>
              <MessageContent className="medi-msg-content">
                <div className="spinner" />
              </MessageContent>
            </Message>
          ) : null}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {error ? (
        <div className="notice urgent" style={{ margin: "0 16px 8px" }}>
          <AlertTriangle size={16} />
          <span>{error.message || "发送失败，请稍后重试"}</span>
        </div>
      ) : null}

      <div className="chat-composer streaming-composer streaming-chat-composer">
        {onUseProfileChange || onUseMemoryChange ? (
          <div className="composer-toggles">
            {onUseProfileChange ? (
              <label className="checkbox composer-profile">
                <input
                  type="checkbox"
                  checked={useProfile}
                  onChange={(event) => onUseProfileChange(event.target.checked)}
                />
                使用我的健康画像
              </label>
            ) : null}
            {onUseMemoryChange ? (
              <label className="checkbox composer-profile">
                <input
                  type="checkbox"
                  checked={useMemory}
                  onChange={(event) => onUseMemoryChange(event.target.checked)}
                />
                使用多轮会话记忆
              </label>
            ) : null}
          </div>
        ) : null}
        {useProfile && !hasProfile ? (
          <p className="composer-hint">
            尚未填写健康画像，请先完善 <Link href="/profile">我的画像</Link>
          </p>
        ) : null}
        {useProfile && hasProfile && profileTags.length > 0 ? (
          <div className="tag-row composer-tags">
            {profileTags.slice(0, 8).map((tag) => (
              <span className="tag neutral" key={tag}>
                {tag}
              </span>
            ))}
          </div>
        ) : null}
        <PromptInput
          className="medi-prompt"
          onSubmit={async (message) => {
            const text = message.text.trim();
            if (!text || busy || !conversationId) return;
            await sendMessage({ text });
          }}
        >
          <PromptInputBody>
            <PromptInputTextarea placeholder={placeholder} />
          </PromptInputBody>
          <PromptInputFooter>
            <PromptInputTools />
            <PromptInputSubmit status={status} onStop={stop} />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}

export function ConversationSidebar({
  items,
  activeId,
  onSelect,
  onCreate,
  creating,
}: {
  items: { conversation_id: string; title: string; preview: string }[];
  activeId: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  creating?: boolean;
}) {
  return (
    <aside className="panel conversation-sidebar">
      <header className="panel-head">
        <div>
          <h2>咨询记录</h2>
        </div>
        <button
          title="新建咨询"
          aria-label="新建咨询"
          className="icon-button"
          disabled={creating}
          onClick={onCreate}
        >
          <Plus size={19} />
        </button>
      </header>
      <div className="conversation-list">
        {items.map((conversation) => (
          <button
            key={conversation.conversation_id}
            className={`conversation-item ${conversation.conversation_id === activeId ? "active" : ""}`}
            onClick={() => onSelect(conversation.conversation_id)}
          >
            <strong>{conversation.title}</strong>
            <small>{conversation.preview || "等待输入问题"}</small>
          </button>
        ))}
      </div>
    </aside>
  );
}
