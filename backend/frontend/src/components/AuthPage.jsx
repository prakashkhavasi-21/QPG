// src/components/AuthPage.jsx
import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signInWithPopup,
  sendPasswordResetEmail
} from 'firebase/auth';
import { auth, googleProvider, db } from '../firebase';
import googleLogo from '../assets/google-logo.png';
import { doc, setDoc, getDoc } from "firebase/firestore";

export default function AuthPage() {
  const [mode, setMode] = useState('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const [info, setInfo] = useState('');

  const handleEmailAuth = async () => {
    setError('');
    if (mode === 'signup' && password !== confirmPassword) {
      setError("Passwords don't match");
      return;
    }
    try {
      let userCred;
      if (mode === 'signin') {
        userCred = await signInWithEmailAndPassword(auth, email, password);
      } else {
        userCred = await createUserWithEmailAndPassword(auth, email, password);
        // give 1 free credit on signup
        await setDoc(doc(db, "users", userCred.user.uid), {
          credits: 1,
          subscriptionExpires: null
        });
      }
      navigate('/app');
    } catch (e) {
      setError(e.message.replace('Firebase:', '').trim());
    }
  };

  const handleGoogle = async () => {
    setError('');
    try {
      const userCred = await signInWithPopup(auth, googleProvider);
      const userRef  = doc(db, "users", userCred.user.uid);
      const userSnap = await getDoc(userRef);

      // If this is the first time signing in with Google, give them 1 free credit
      if (!userSnap.exists()) {
        await setDoc(userRef, {
          credits: 1,
          subscriptionExpires: null
        });
      }

      navigate('/app');
    } catch (e) {
      setError(e.message.replace('Firebase:', '').trim());
    }
  };

  const handleForgotPassword = async () => {
       setError('');
       setInfo('');
       if (!email) {
         setError('Please enter your email address to reset password.');
         return;
       }
       try {
         await sendPasswordResetEmail(auth, email);
         setInfo('Password reset email sent! Please check your inbox.');
       } catch (e) {
         setError(e.message.replace('Firebase:', '').trim());
       }
  };

  return (
    <div className="container my-5 pt-5">
      <div className="col-12 col-md-8 col-lg-12 mx-auto">
        <div className="card p-4 shadow">
          <div className="text-center mb-4">
            <h2 className="fw-bold">
              {mode === 'signin' ? 'Welcome back' : 'Create new account'}
            </h2>
            {mode === 'signin' && (
              <p className="text-muted">Login to manage your account.</p>
            )}
          </div>

          {/* Google Button */}
          <button
            onClick={handleGoogle}
            className="btn btn-light w-100 d-flex align-items-center justify-content-center mb-3 border"
          >
            <img
              src={googleLogo}
              alt="Google"
              style={{ height: 20, width: 20, marginRight: 10 }}
            />
            Sign in with Google
          </button>

          {/* Divider */}
          <div className="d-flex align-items-center my-3">
            <hr className="flex-grow-1" />
            <span className="px-2 text-muted">or</span>
            <hr className="flex-grow-1" />
          </div>

          {info && (
           <div className="alert alert-success py-2 text-center">
             {info}
           </div>
         )} 

          {/* Error Message */}
          {error && (
            <div className="alert alert-danger py-2 text-center">
              {error}
            </div>
          )}

          {/* Email Input */}
          <div className="mb-3">
            <label className="form-label">Your Email</label>
            <input
              type="email"
              placeholder="email@site.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="form-control"
            />
          </div>

          {/* Password Input */}
          <div className="mb-3">
            <div className="d-flex justify-content-between mb-1">
              <label className="form-label">Password</label>
              {mode === 'signin' && (
                <button
                  onClick={handleForgotPassword}
                  className="btn btn-link p-0"
                  type="button"
                >
                  Forgot password?
                </button>
              )}
            </div>
            <div className="input-group">
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="8+ characters required"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="form-control"
              />
              <button
                onClick={() => setShowPassword(v => !v)}
                type="button"
                className="btn btn-outline-secondary"
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          {/* Confirm Password */}
          {mode === 'signup' && (
            <div className="mb-3">
              <label className="form-label">Confirm Password</label>
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="Re-enter password"
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                className="form-control"
              />
            </div>
          )}

          {/* Submit Button */}
          <button
            onClick={handleEmailAuth}
            className="btn btn-primary w-100 mb-2"
          >
            {mode === 'signin' ? 'Login' : 'Sign up'}
          </button>

          {/* Toggle Mode */}
          <p className="text-center text-muted small mt-3">
            {mode === 'signin'
              ? "Don't have an account yet? "
              : 'Already have an account? '}
            <button
              onClick={() => {
                setError('');
                setMode(m => (m === 'signin' ? 'signup' : 'signin'));
              }}
              className="btn btn-link p-0"
              type="button"
            >
              {mode === 'signin' ? 'Create New Account' : 'Login'}
            </button>
          </p>        
        </div>
        <div>
          <p className="text-center text-muted small mt-3">
            By signing up, you agree to our Our Policies<br />
              <Link to={`/LegalContactPage`} style={{color:'blue'}}>Terms and Conditions</Link> Apply
          </p>
        </div>
      </div>
    </div>
  );
}
