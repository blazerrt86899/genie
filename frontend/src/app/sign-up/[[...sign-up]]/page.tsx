import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      {/* → /welcome polls GET /users/me before entering /chat (webhook race, §7.8) */}
      <SignUp forceRedirectUrl="/welcome" signInUrl="/sign-in" />
    </div>
  );
}
