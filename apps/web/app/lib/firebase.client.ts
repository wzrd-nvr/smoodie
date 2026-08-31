/**
 * Firebase browser SDK, initialized lazily from server-provided config.
 *
 * The client only ever holds an ID token long enough to trade it for a session
 * cookie; it is never persisted, which is why persistence is set to none.
 */

import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  inMemoryPersistence,
  setPersistence,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  updateProfile,
  type Auth,
} from "firebase/auth";

export type FirebaseConfig = {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
};

let app: FirebaseApp | undefined;
let auth: Auth | undefined;

function getAuthClient(config: FirebaseConfig): Auth {
  if (!app) {
    app = getApps()[0] ?? initializeApp(config);
  }
  if (!auth) {
    auth = getAuth(app);
    // The session cookie is the durable credential; the SDK holds nothing.
    void setPersistence(auth, inMemoryPersistence);
  }
  return auth;
}

/** Maps Firebase's error codes to something a person can act on. */
export function describeAuthError(code: string): string {
  switch (code) {
    case "auth/invalid-email":
      return "That doesn't look like an email address.";
    case "auth/missing-password":
      return "Enter your password.";
    case "auth/weak-password":
      return "Passwords need at least 6 characters.";
    case "auth/email-already-in-use":
      return "There's already an account with that email. Try signing in.";
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      // Deliberately identical for all three: distinguishing them would tell an
      // attacker which emails have accounts.
      return "That email and password don't match.";
    case "auth/too-many-requests":
      return "Too many attempts. Wait a moment and try again.";
    case "auth/network-request-failed":
      return "Couldn't reach the network. Check your connection.";
    default:
      return "Couldn't sign you in. Try again.";
  }
}

export async function signIn(
  config: FirebaseConfig,
  email: string,
  password: string,
): Promise<string> {
  const credential = await signInWithEmailAndPassword(
    getAuthClient(config),
    email,
    password,
  );
  return credential.user.getIdToken();
}

export async function signUp(
  config: FirebaseConfig,
  email: string,
  password: string,
  displayName?: string,
): Promise<string> {
  const credential = await createUserWithEmailAndPassword(
    getAuthClient(config),
    email,
    password,
  );
  if (displayName) {
    await updateProfile(credential.user, { displayName });
  }
  // Re-issued so the token carries the display name the API reads at signup.
  return credential.user.getIdToken(true);
}
