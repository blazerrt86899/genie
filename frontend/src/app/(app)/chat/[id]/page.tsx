import { Suspense } from "react";
import { ChatView } from "@/components/chat/ChatView";

export default async function ConversationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Suspense fallback={null}>
      <ChatView conversationId={id} />
    </Suspense>
  );
}
