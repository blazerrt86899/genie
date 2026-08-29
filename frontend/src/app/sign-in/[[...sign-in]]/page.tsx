import { SignIn } from "@clerk/nextjs";
import { CLERK_ENABLED } from "@/lib/clerk";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      {CLERK_ENABLED ? (
        <SignIn />
      ) : (
        <p className="text-sm text-muted-foreground">
          Clerk is not configured — the app runs in public dev mode. Set
          <code className="mx-1">NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY</code>
          to enable auth.
        </p>
      )}
    </div>
  );
}
