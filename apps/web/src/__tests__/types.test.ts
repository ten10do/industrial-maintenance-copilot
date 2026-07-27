import '@testing-library/jest-dom';
import { ApiError, STATUS_LABELS, PRIORITY_LABELS, LOG_TYPE_LABELS, URGENCY_LABELS, FAULT_REPORT_STATUS_LABELS } from '@/lib/types';

describe('ApiError', () => {
  it('用字符串消息构造', () => {
    const err = new ApiError(500, '服务器内部错误');
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe('ApiError');
    expect(err.message).toBe('服务器内部错误');
    expect(err.status).toBe(500);
  });

  it('用对象消息构造', () => {
    const err = new ApiError(409, { code: 'DUPLICATE', message: '已存在关联', work_order_id: 7 });
    expect(err.message).toBe('已存在关联');
    expect(err.code).toBe('DUPLICATE');
    expect(err.workOrderId).toBe(7);
  });

  it('无 message 时用 HTTP status 兜底', () => {
    const err = new ApiError(404, { code: 'NOT_FOUND' });
    expect(err.message).toBe('HTTP 404');
  });

  it('构造 400 错误', () => {
    const err = new ApiError(400, '参数错误');
    expect(err.status).toBe(400);
    expect(err.message).toBe('参数错误');
  });

  it('构造 401 错误', () => {
    const err = new ApiError(401, '未认证');
    expect(err.status).toBe(401);
    expect(err.message).toBe('未认证');
  });

  it('构造 403 错误', () => {
    const err = new ApiError(403, '权限不足');
    expect(err.status).toBe(403);
    expect(err.message).toBe('权限不足');
  });
});

describe('Label Constants', () => {
  it('STATUS_LABELS 全部映射正确', () => {
    expect(STATUS_LABELS.pending_dispatch).toBe('待分派');
    expect(STATUS_LABELS.assigned).toBe('已分派');
    expect(STATUS_LABELS.accepted).toBe('已接受');
    expect(STATUS_LABELS.in_progress).toBe('处理中');
    expect(STATUS_LABELS.pending_acceptance).toBe('待验收');
    expect(STATUS_LABELS.completed).toBe('已完成');
    expect(STATUS_LABELS.cancelled).toBe('已取消');
    expect(STATUS_LABELS.returned).toBe('已退回');
    expect(STATUS_LABELS.paused).toBe('暂停');
  });

  it('PRIORITY_LABELS 全部映射正确', () => {
    expect(PRIORITY_LABELS.P1).toBe('P1 紧急');
    expect(PRIORITY_LABELS.P2).toBe('P2 高');
    expect(PRIORITY_LABELS.P3).toBe('P3 中');
    expect(PRIORITY_LABELS.P4).toBe('P4 低');
  });

  it('LOG_TYPE_LABELS 全部映射正确', () => {
    expect(LOG_TYPE_LABELS.inspect).toBe('检查');
    expect(LOG_TYPE_LABELS.diagnose).toBe('诊断');
    expect(LOG_TYPE_LABELS.repair).toBe('维修');
    expect(LOG_TYPE_LABELS.replace).toBe('更换');
    expect(LOG_TYPE_LABELS.test).toBe('测试');
    expect(LOG_TYPE_LABELS.note).toBe('备注');
  });

  it('URGENCY_LABELS 全部映射正确', () => {
    expect(URGENCY_LABELS.low).toBe('低');
    expect(URGENCY_LABELS.medium).toBe('中');
    expect(URGENCY_LABELS.high).toBe('高');
    expect(URGENCY_LABELS.critical).toBe('紧急');
  });

  it('FAULT_REPORT_STATUS_LABELS 全部映射正确', () => {
    expect(FAULT_REPORT_STATUS_LABELS.pending).toBe('待处理');
    expect(FAULT_REPORT_STATUS_LABELS.converted).toBe('已转工单');
    expect(FAULT_REPORT_STATUS_LABELS.closed).toBe('已关闭');
  });
});
