import LoginForm, { DemoLoginConfig } from './login-form';

const demoLogin: DemoLoginConfig | null = process.env.NODE_ENV === 'production'
  ? null
  : {
      email: 'admin@example.com',
      password: 'Demo123456',
      accounts: [
        { email: 'admin@example.com', label: '管理员', color: 'bg-primary/10 text-primary-300 border-primary/30' },
        { email: 'supervisor@example.com', label: '主管', color: 'bg-warning/10 text-warning border-warning/30' },
        { email: 'tech1@example.com', label: '工程师', color: 'bg-success/10 text-green-400 border-green-400/30' },
      ],
    };

export default function LoginPage() {
  return <LoginForm demoLogin={demoLogin} />;
}
