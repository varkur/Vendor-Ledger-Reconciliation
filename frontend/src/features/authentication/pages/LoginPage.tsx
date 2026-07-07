/**
 * Login Page - Emcure Theme (Red primary, clean card design).
 * POST /api/v1/auth/login
 */

import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { InputText } from 'primereact/inputtext';
import { Password } from 'primereact/password';
import { Button } from 'primereact/button';
import { Divider } from 'primereact/divider';
import { Message } from 'primereact/message';
import { useAppDispatch, useAppSelector } from '@app/store';
import { loginThunk, clearError } from '../store/authSlice';
import { microsoftApi } from '../api/microsoftApi';
import emcureLogo from '@assets/images/emcure-logo.svg';


const loginSchema = z.object({
  username: z.string().min(3, 'Username must be at least 3 characters'),
  password: z.string().min(1, 'Password is required'),
});

type LoginFormData = z.infer<typeof loginSchema>;

export const LoginPage = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { isLoading, error } = useAppSelector((state) => state.auth);
  const [msLoading, setMsLoading] = useState(false);

  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormData) => {
    dispatch(clearError());
    const result = await dispatch(loginThunk(data));
    if (loginThunk.fulfilled.match(result)) {
      const redirect = sessionStorage.getItem('redirectAfterLogin') || '/manage-party';
      sessionStorage.removeItem('redirectAfterLogin');
      navigate(redirect);
    }
  };

  const handleMicrosoftLogin = async () => {
    setMsLoading(true);
    try {
      const res = await microsoftApi.getLoginUrl();
      window.location.href = res.auth_url;
    } catch {
      dispatch(clearError());
      // Show error inline
      setMsLoading(false);
    }
  };

  return (
    <div
      className="flex align-items-center justify-content-center min-h-screen"
      style={{ background: 'linear-gradient(135deg, #FFF0F0 0%, #F8F9FA 100%)' }}
    >
      <div className="em-login-card p-6 w-full" style={{ maxWidth: '420px' }}>
        {/* Logo / Header */}
        <div className="text-center mb-5">
          <div
            className="text-3xl font-bold mb-2"
            style={{ color: 'var(--color-primary)' }}
          >
            <img src={emcureLogo} alt="Emcure — cure and beyond" style={{ height: '56px', width: 'auto' }} />
          </div>
          <span style={{ color: 'var(--color-text-secondary)' }}>
            Enterprise App Template
          </span>
        </div>

        {/* Error Message */}
        {error && (
          <Message severity="error" text={error} className="w-full mb-4" />
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="mb-4">
            <label
              htmlFor="username"
              className="block font-medium mb-2"
              style={{ color: 'var(--color-text-primary)', fontSize: '14px' }}
            >
              Username
            </label>
            <InputText
              id="username"
              {...register('username')}
              placeholder="Enter username"
              className={`w-full ${errors.username ? 'p-invalid' : ''}`}
              aria-label="Username"
              aria-describedby="username-error"
            />
            {errors.username && (
              <small id="username-error" className="p-error mt-1 block">
                {errors.username.message}
              </small>
            )}
          </div>

          <div className="mb-5">
            <label
              htmlFor="password"
              className="block font-medium mb-2"
              style={{ color: 'var(--color-text-primary)', fontSize: '14px' }}
            >
              Password
            </label>
            <Controller
              name="password"
              control={control}
              render={({ field }) => (
                <Password
                  id="password"
                  {...field}
                  placeholder="Enter password"
                  toggleMask
                  feedback={false}
                  className={`w-full ${errors.password ? 'p-invalid' : ''}`}
                  inputClassName="w-full"
                  aria-label="Password"
                  aria-describedby="password-error"
                />
              )}
            />
            {errors.password && (
              <small id="password-error" className="p-error mt-1 block">
                {errors.password.message}
              </small>
            )}
          </div>

          <Button
            type="submit"
            label="Sign In"
            icon="pi pi-sign-in"
            className="w-full"
            loading={isLoading}
            aria-label="Sign in"
          />
        </form>

        {/* Divider */}
        <Divider align="center" className="my-4">
          <span style={{ color: 'var(--color-text-muted)', fontSize: '12px' }}>OR</span>
        </Divider>

        {/* Microsoft SSO Button */}
        <Button
          type="button"
          label="Sign in with Microsoft"
          icon="pi pi-microsoft"
          className="w-full p-button-outlined"
          loading={msLoading}
          onClick={handleMicrosoftLogin}
          aria-label="Sign in with Microsoft"
          style={{
            borderColor: 'var(--color-surface-border)',
            color: 'var(--color-text-primary)',
          }}
        />
      </div>
    </div>
  );
};
