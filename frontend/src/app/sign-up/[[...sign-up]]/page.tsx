import { SignUp } from "@clerk/nextjs";
import { CLERK_ENABLED } from "@/lib/clerk";

export default function SignUpPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      {CLERK_ENABLED ? (
        <SignUp />
      ) : (
        <p className="text-sm text-muted-foreground">
          Clerk is not configured — the app runs in public dev mode.
        </p>
      )}
    </div>
  );
}
