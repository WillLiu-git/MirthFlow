from flask import Flask, render_template, jsonify, redirect, url_for
import os
import sys
import json
import subprocess
import signal
import time
import webbrowser
from functools import lru_cache
from datetime import datetime
import logging

# 添加DetectionSystem到路径，以便导入common模块
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DetectionSystem'))

try:
    from common.paths import get_log_paths, get_alerts_file, get_hotspot_hunter_output_dir, get_vcs_output_dir, ensure_directories
    # 确保目录存在
    ensure_directories()
except ImportError:
    # 如果导入失败，使用相对路径作为后备方案
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    def get_log_paths():
        return {
            'HotspotHunter': os.path.join(BASE_DIR, 'DetectionSystem', 'HotspotHunter', 'resource', 'HotspotHunter.log'),
            'RiskAnalyzer': os.path.join(BASE_DIR, 'DetectionSystem', 'RiskAnalyzer', 'resource', 'RiskAnalyzer.log'),
            'VideosCommentsSpotter': os.path.join(BASE_DIR, 'DetectionSystem', 'VideosCommentsSpotter', 'resource', 'VideosCommentsSpotter.log'),
            'System': os.path.join(BASE_DIR, 'logs', 'system.log')
        }
    def get_alerts_file():
        return os.path.join(BASE_DIR, 'DetectionSystem', 'RiskAnalyzer', 'resource', 'system_alerts.json')
    def get_hotspot_hunter_output_dir():
        return os.path.join(BASE_DIR, 'DetectionSystem', 'hotspot_hunter_output')
    def get_vcs_output_dir():
        return os.path.join(BASE_DIR, 'DetectionSystem', 'VideosCommentsSpotter', 'output')

# 系统状态文件路径
SYSTEM_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.system_state')
# 系统进程信息文件路径
SYSTEM_PROCESS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.system_process')

# 全局变量，用于存储系统进程
_system_process = None
# 初始化时尝试从文件中恢复进程信息
if os.path.exists(SYSTEM_PROCESS_FILE):
    try:
        with open(SYSTEM_PROCESS_FILE, 'r', encoding='utf-8') as f:
            process_info = json.load(f)
        # 不使用psutil，直接保存进程信息，在需要时再检查
        _system_process = {'pid': process_info.get('pid'), 'type': 'recovered'}
    except Exception as e:
        logging.error(f"恢复进程信息失败: {str(e)}")
        # 删除无效的进程信息文件
        if os.path.exists(SYSTEM_PROCESS_FILE):
            os.remove(SYSTEM_PROCESS_FILE)

app = Flask(__name__)

# 配置日志，减少不必要的输出
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)  # 只输出错误级别以上的日志

# 配置日志文件路径（使用统一路径管理）
LOG_PATHS = get_log_paths()

# 配置预警报告文件路径（使用统一路径管理）
ALERTS_FILE = get_alerts_file()

@app.route('/')
def index():
    """主页面，显示系统状态和agent列表"""
    # 排除System键，单独处理系统日志
    agents = [agent for agent in LOG_PATHS.keys() if agent != 'System']
    return render_template('index.html', agents=agents, datetime=datetime)



@app.route('/alerts')
def alerts():
    """显示最终预警报告"""
    alerts_list = []
    
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, 'r', encoding='utf-8') as f:
            alerts_list = json.load(f)
    
    # 计算统计信息
    stats = {
        'total': len(alerts_list),
        'critical': sum(1 for a in alerts_list if a.get('alert_level') == '紧急'),
        'important': sum(1 for a in alerts_list if a.get('alert_level') == '重要'),
        'info': sum(1 for a in alerts_list if a.get('alert_level') == '信息')
    }
    
    return render_template('alerts.html', alerts=alerts_list, stats=stats)

def read_log_file(log_path):
    """读取日志文件，支持多种编码，返回最近200行"""
    try:
        if os.path.exists(log_path):
            # 检查文件大小，如果是空文件，直接返回空列表
            if os.path.getsize(log_path) == 0:
                return [f"日志文件 {log_path} 为空"]
            
            # 尝试使用不同编码读取日志文件
            encodings = ['utf-8', 'gbk', 'utf-16', 'latin-1']
            log_content = None
            
            for encoding in encodings:
                try:
                    with open(log_path, 'r', encoding=encoding) as f:
                        log_content = f.readlines()
                    break
                except UnicodeDecodeError:
                    continue
            
            if log_content is not None:
                # 返回最近200行日志
                return log_content[-200:]
            else:
                return [f"无法读取日志文件 {log_path}，编码错误"]
        else:
            return [f"日志文件不存在: {log_path}"]
    except Exception as e:
        return [f"读取日志文件时出错: {str(e)}"]

@app.route('/api/logs/<agent_name>')
def api_logs(agent_name):
    """API端点，返回特定agent的最新日志"""
    if agent_name not in LOG_PATHS:
        return jsonify({'error': f'Agent {agent_name} 不存在'}), 404
    
    log_path = LOG_PATHS[agent_name]
    logs = read_log_file(log_path)
    
    return jsonify({'logs': logs, 'agent_name': agent_name})

def get_system_state():
    """获取系统状态"""
    if os.path.exists(SYSTEM_STATE_FILE):
        try:
            with open(SYSTEM_STATE_FILE, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except:
            return 'stopped'
    return 'stopped'

def set_system_state(state):
    """设置系统状态: running, paused, stopped"""
    try:
        with open(SYSTEM_STATE_FILE, 'w', encoding='utf-8') as f:
            f.write(state)
    except Exception as e:
        logging.error(f"设置系统状态失败: {str(e)}")

@app.route('/start')
def start_system():
    """启动系统"""
    global _system_process
    
    # 检查系统是否已运行
    process_is_running = False
    if _system_process is not None:
        try:
            if isinstance(_system_process, dict):
                # 对于字典类型的进程信息，不使用psutil检查，直接认为已停止
                # 因为psutil可能不可用，且进程对象已不再可用
                process_is_running = False
            elif hasattr(_system_process, 'poll'):
                # 对于subprocess.Popen对象，使用poll()方法（标准库，不需要psutil）
                if _system_process.poll() is None:
                    process_is_running = True
        except Exception as e:
            logging.error(f"检查进程状态失败: {str(e)}")
            _system_process = None
    
    # 如果系统已运行，则继续运行（取消暂停）
    if process_is_running:
        # 系统正在运行，检查是否暂停
        current_state = get_system_state()
        if current_state == 'paused':
            # 取消暂停
            set_system_state('running')
        return redirect(url_for('index'))
    
    # 启动新系统
    try:
        # 获取项目根目录
        project_root = os.path.dirname(os.path.abspath(__file__))
        # 启动系统主程序，不使用shell=True以提高安全性
        process_obj = subprocess.Popen(
            ['python', 'main.py'],
            cwd=project_root,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        # 直接保存subprocess.Popen对象，不使用字典包装
        _system_process = process_obj
        # 保存进程信息到文件
        with open(SYSTEM_PROCESS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'pid': process_obj.pid}, f)
        # 设置系统状态为运行中
        set_system_state('running')
    except Exception as e:
        logging.error(f"启动系统失败: {str(e)}")
        set_system_state('stopped')
        _system_process = None
        # 删除无效的进程信息文件
        if os.path.exists(SYSTEM_PROCESS_FILE):
            os.remove(SYSTEM_PROCESS_FILE)
    
    return redirect(url_for('index'))

@app.route('/pause')
def pause_system():
    """暂停系统（不停止进程，只是暂停执行）"""
    global _system_process
    
    # 检查系统是否在运行
    process_is_running = False
    if _system_process is not None:
        try:
            # 只检查subprocess.Popen对象，不使用psutil
            if hasattr(_system_process, 'poll'):
                # 对于subprocess.Popen对象，使用poll()方法（标准库，不需要psutil）
                if _system_process.poll() is None:
                    process_is_running = True
        except Exception as e:
            logging.error(f"检查进程状态失败: {str(e)}")
            _system_process = None
    
    if process_is_running:
        # 设置状态为暂停
        set_system_state('paused')
        logging.info("系统已暂停")
    else:
        logging.warning("系统未运行，无法暂停")
    
    return redirect(url_for('index'))

@app.route('/resume')
def resume_system():
    """恢复系统"""
    global _system_process
    
    # 检查系统是否在运行
    process_is_running = False
    if _system_process is not None:
        try:
            # 只检查subprocess.Popen对象，不使用psutil
            if hasattr(_system_process, 'poll'):
                # 对于subprocess.Popen对象，使用poll()方法（标准库，不需要psutil）
                if _system_process.poll() is None:
                    process_is_running = True
        except Exception as e:
            logging.error(f"检查进程状态失败: {str(e)}")
            _system_process = None
    
    if process_is_running:
        # 设置状态为运行
        set_system_state('running')
        logging.info("系统已恢复运行")
    else:
        logging.warning("系统未运行，无法恢复")
    
    return redirect(url_for('index'))

@app.route('/stop')
def stop_system():
    """中止系统：停止进程、清除日志和报告，然后关闭浏览器"""
    global _system_process
    
    # 1. 停止系统主程序
    process_pid = None
    if _system_process is not None:
        try:
            # 只处理subprocess.Popen对象，不使用psutil
            if hasattr(_system_process, 'pid'):
                process_pid = _system_process.pid
            
            # 尝试终止进程
            if process_pid:
                # 在Windows中使用taskkill命令确保所有子进程都被终止
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(process_pid)], shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                time.sleep(2)  # 增加等待时间
            
            # 对于subprocess.Popen对象，尝试使用terminate和kill
            if hasattr(_system_process, 'terminate'):
                _system_process.terminate()
                time.sleep(1)
                if hasattr(_system_process, 'poll') and _system_process.poll() is None:
                    _system_process.kill()
                    time.sleep(1)
        except Exception as e:
            logging.error(f"停止系统进程失败: {str(e)}")
        finally:
            _system_process = None
    
    # 2. 清除状态文件
    set_system_state('stopped')
    
    # 3. 删除进程信息文件
    if os.path.exists(SYSTEM_PROCESS_FILE):
        try:
            os.remove(SYSTEM_PROCESS_FILE)
        except Exception as e:
            logging.error(f"删除进程信息文件失败: {str(e)}")
    
    # 4. 清除日志和报告（清除Flask上显示的内容）
    try:
        clear_logs()
        logging.info("已清除所有日志和报告")
    except Exception as e:
        logging.error(f"清除日志和报告失败: {str(e)}")
    
    # 5. 返回关闭页面（提示用户关闭浏览器）
    return render_template('exit.html', message='系统已中止，所有日志和报告已清除。请关闭浏览器窗口。')

@app.route('/api/system_status')
def api_system_status():
    """获取系统状态"""
    global _system_process
    
    status = {
        'running': False,
        'paused': False,
        'stopped': True,
        'pid': None,
        'state': 'stopped',
        'uptime': 0  # 添加运行时间字段
    }
    
    # 检查系统进程是否正在运行
    process_running = False
    process_pid = None
    
    # 1. 首先检查全局变量（只使用标准库，不依赖psutil）
    if _system_process is not None:
        try:
            # 只检查subprocess.Popen对象，不使用psutil
            if hasattr(_system_process, 'poll'):
                # 对于subprocess.Popen对象，使用poll()方法（标准库，不需要psutil）
                if _system_process.poll() is None:
                    process_running = True
                    process_pid = _system_process.pid
        except Exception as e:
            logging.error(f"检查全局进程对象失败: {str(e)}")
            _system_process = None
    
    # 2. 如果全局变量不存在或进程已结束，不使用psutil检查文件中的进程
    # 因为psutil可能不可用，且无法可靠地检查进程是否仍在运行
    if os.path.exists(SYSTEM_PROCESS_FILE) and not process_running:
        # 如果有进程文件但全局进程对象不存在，删除无效的进程文件
        try:
            os.remove(SYSTEM_PROCESS_FILE)
        except Exception as e:
            logging.error(f"删除无效进程文件失败: {str(e)}")
    
    # 获取当前状态文件中的状态
    system_state = get_system_state()
    
    if process_running:
        # 进程正在运行
        status['running'] = True
        status['pid'] = process_pid
        status['state'] = system_state
        if system_state == 'paused':
            status['paused'] = True
            status['stopped'] = False
        elif system_state == 'running':
            status['paused'] = False
            status['stopped'] = False
            # 计算运行时间（简单实现，从启动时间到现在）
            try:
                if hasattr(_system_process, 'start_time'):
                    # 如果进程对象有start_time属性，直接使用
                    status['uptime'] = int(time.time() - _system_process.start_time)
                else:
                    # 否则，我们可以从进程创建时间估算
                    # 这里使用当前时间减去进程创建时间的近似值
                    status['uptime'] = int(time.time() - os.path.getctime(SYSTEM_PROCESS_FILE))
            except:
                # 如果无法获取运行时间，返回0
                status['uptime'] = 0
    else:
        # 进程未运行，确保状态文件也更新为stopped
        status['state'] = 'stopped'
        set_system_state('stopped')
        # 删除无效的进程信息文件
        if os.path.exists(SYSTEM_PROCESS_FILE):
            try:
                os.remove(SYSTEM_PROCESS_FILE)
            except Exception as e:
                logging.error(f"删除进程信息文件失败: {str(e)}")
    
    return jsonify(status)

@app.route('/exit')
def exit_system():
    """退出系统，关闭界面并清除日志和报告"""
    global _system_process
    
    # 1. 停止系统主程序
    if _system_process is not None and _system_process.poll() is None:
        try:
            # 在Windows中使用taskkill命令确保所有子进程都被终止
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(_system_process.pid)], shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(1)
            # 作为后备方案，使用terminate和kill
            if _system_process.poll() is None:
                _system_process.terminate()
                time.sleep(1)
                if _system_process.poll() is None:
                    _system_process.kill()
        except Exception as e:
            logging.error(f"退出时停止系统进程失败: {str(e)}")
        finally:
            _system_process = None
    
    # 2. 清除日志和报告
    clear_logs()
    
    # 3. 返回退出页面
    return render_template('exit.html')

@app.route('/api/exit')
def api_exit():
    """API端点，退出系统并清除日志和报告"""
    global _system_process
    
    # 1. 停止系统主程序
    if _system_process is not None and _system_process.poll() is None:
        try:
            # 在Windows中使用taskkill命令确保所有子进程都被终止
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(_system_process.pid)], shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(1)
            # 作为后备方案，使用terminate和kill
            if _system_process.poll() is None:
                _system_process.terminate()
                time.sleep(1)
                if _system_process.poll() is None:
                    _system_process.kill()
        except Exception as e:
            logging.error(f"API退出时停止进程失败: {str(e)}")
        finally:
            _system_process = None
    
    # 2. 清除日志和报告
    clear_logs()
    
    return jsonify({'message': '系统已退出'})

@app.route('/api/report/<agent_name>')
def api_report(agent_name):
    """API端点，返回特定agent的最新LLM报告"""
    if agent_name not in LOG_PATHS:
        return jsonify({'error': f'Agent {agent_name} 不存在'}), 404
    
    # 获取最新报告
    report = get_latest_report(agent_name)
    
    return jsonify({'report': report, 'agent_name': agent_name})

@app.route('/logs/<agent_name>')
def agent_logs(agent_name):
    """显示特定agent的日志和报告"""
    if agent_name not in LOG_PATHS:
        return f"Agent {agent_name} 不存在", 404
    
    log_path = LOG_PATHS[agent_name]
    logs = read_log_file(log_path)
    
    # 获取最新报告
    report = get_latest_report(agent_name)
    
    return render_template('logs.html', agent_name=agent_name, logs=logs, report=report, datetime=datetime)

@app.route('/system_logs')
def system_logs():
    """显示系统日志（main.py的输出）"""
    log_path = LOG_PATHS['System']
    logs = read_log_file(log_path)
    
    return render_template('system_logs.html', logs=logs, datetime=datetime)

def get_latest_report(agent_name):
    """获取特定agent的最新LLM报告"""
    import glob
    
    # 基础报告结构
    base_report = {
        'summary': f'{agent_name} 报告',
        'alert_level': '信息',
        'risk_level': '低',
        'risk_factors': [],
        'recommendations': [f'暂无最新报告，{agent_name}正在运行中'],
        'report_source': agent_name,
        'generated_time': time.time()
    }
    
    # 根据不同agent获取报告
    if agent_name == 'HotspotHunter':
        report_dir = get_hotspot_hunter_output_dir()
        report_pattern = os.path.join(report_dir, 'hotspot_report_*.json')
        
        # 获取最新报告文件
        report_files = glob.glob(report_pattern)
        if report_files:
            latest_report_file = max(report_files, key=os.path.getctime)
            try:
                with open(latest_report_file, 'r', encoding='utf-8') as f:
                    report = json.load(f)
                    
                    # 合并基础报告字段
                    report.update(base_report)
                    report['file_name'] = os.path.basename(latest_report_file)
                    report['generated_time'] = os.path.getctime(latest_report_file)
                    
                    # 确保报告包含完整的风险项目信息
                    if 'topics' in report:
                        report['risk_items'] = report['topics']
                    
                    return report
            except Exception as e:
                logging.error(f"读取HotspotHunter报告失败: {str(e)}")
                return base_report
        return base_report
    
    elif agent_name == 'RiskAnalyzer':
        report_path = get_alerts_file()
        if os.path.exists(report_path):
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    alerts = json.load(f)
                    if alerts:
                        latest_alert = alerts[-1]
                        latest_alert['report_source'] = 'RiskAnalyzer'
                        latest_alert['file_name'] = 'system_alerts.json'
                        latest_alert['total_alerts'] = len(alerts)
                        
                        # 统计预警级别
                        latest_alert['alert_statistics'] = {
                            'critical': sum(1 for a in alerts if a.get('alert_level') == '紧急'),
                            'important': sum(1 for a in alerts if a.get('alert_level') == '重要'),
                            'info': sum(1 for a in alerts if a.get('alert_level') == '信息')
                        }
                        return latest_alert
            except Exception as e:
                logging.error(f"读取RiskAnalyzer报告失败: {str(e)}")
        return base_report
    
    elif agent_name == 'VideosCommentsSpotter':
        report_dir = get_vcs_output_dir()
        report_pattern = os.path.join(report_dir, 'vcs_report_*.json')
        
        # 获取最新报告文件
        report_files = glob.glob(report_pattern)
        if report_files:
            latest_report_file = max(report_files, key=os.path.getctime)
            try:
                with open(latest_report_file, 'r', encoding='utf-8') as f:
                    report = json.load(f)
                    report.update(base_report)
                    report['file_name'] = os.path.basename(latest_report_file)
                    report['generated_time'] = os.path.getctime(latest_report_file)
                    return report
            except Exception as e:
                logging.error(f"读取VideosCommentsSpotter报告失败: {str(e)}")
                return base_report
        return base_report
    
    elif agent_name == 'System':
        # 系统报告简化版本
        system_status = {
            'summary': '舆情监测系统运行状态概览',
            'alert_level': '正常',
            'risk_level': '低',
            'report_source': 'System',
            'generated_time': time.time(),
            'system_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 组件状态检查
        component_status = []
        for component, log_path in LOG_PATHS.items():
            if os.path.exists(log_path):
                log_size = os.path.getsize(log_path)
                last_modified = os.path.getmtime(log_path)
                component_status.append({
                    'name': component,
                    'status': '运行中',
                    'log_size': f"{log_size / 1024:.2f} KB",
                    'last_log_update': datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')
                })
            else:
                component_status.append({
                    'name': component,
                    'status': '未找到日志文件',
                    'log_path': log_path,
                    'log_size': 'N/A',
                    'last_log_update': 'N/A'
                })
        
        system_status['components'] = component_status
        
        # 预警统计
        alerts_path = get_alerts_file()
        if os.path.exists(alerts_path):
            try:
                with open(alerts_path, 'r', encoding='utf-8') as f:
                    alerts = json.load(f)
                    total_alerts = len(alerts)
                    critical_count = sum(1 for a in alerts if a.get('alert_level') == '紧急')
                    important_count = sum(1 for a in alerts if a.get('alert_level') == '重要')
                    info_count = sum(1 for a in alerts if a.get('alert_level') == '信息')
                    
                    system_status['alert_statistics'] = {
                        'total_alerts': total_alerts,
                        'critical': critical_count,
                        'important': important_count,
                        'info': info_count
                    }
                    
                    # 更新预警和风险等级
                    if critical_count > 0:
                        system_status['alert_level'] = '紧急'
                        system_status['risk_level'] = '高'
                        system_status['risk_factors'] = [f"存在 {critical_count} 条紧急预警"]
                        system_status['recommendations'] = ["请立即查看紧急预警信息"]
                    elif important_count > 0:
                        system_status['alert_level'] = '重要'
                        system_status['risk_level'] = '中'
                        system_status['risk_factors'] = [f"存在 {important_count} 条重要预警"]
                        system_status['recommendations'] = ["请查看重要预警信息"]
                    else:
                        system_status['recommendations'] = ["系统运行正常，继续监控"]
            except Exception as e:
                logging.error(f"读取系统预警统计失败: {str(e)}")
                system_status['recommendations'] = ["系统运行正常，继续监控"]
        else:
            system_status['alert_statistics'] = {
                'total_alerts': 0,
                'critical': 0,
                'important': 0,
                'info': 0
            }
            system_status['recommendations'] = ["系统运行正常，继续监控"]
        
        return system_status
    
    else:
        return None

def clear_logs():
    """清除日志和报告"""
    import glob
    
    # 使用统一路径管理获取日志文件路径
    log_files = list(LOG_PATHS.values())
    # 添加错误日志
    try:
        from common.paths import get_path_str
        log_files.append(get_path_str('error_log'))
    except ImportError:
        # 后备方案
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        log_files.append(os.path.join(BASE_DIR, 'logs', 'error.log'))
    
    # 清除所有日志文件
    for log_file in log_files:
        try:
            if os.path.exists(log_file):
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write('')
        except Exception as e:
            logging.error(f"清除日志文件失败 {log_file}: {str(e)}")
    
    # 清除报告文件
    report_files = [
        # 清除预警信息文件
        get_alerts_file(),
        # 清除HotspotHunter报告
        os.path.join(get_hotspot_hunter_output_dir(), '*.json'),
        # 清除VideosCommentsSpotter报告
        os.path.join(get_vcs_output_dir(), 'vcs_report_*.json')
    ]
    
    # 清除所有报告文件
    for report_pattern in report_files:
        # 处理通配符
        if '*' in report_pattern:
            for report_file in glob.glob(report_pattern):
                try:
                    if os.path.exists(report_file):
                        os.remove(report_file)
                except Exception as e:
                    logging.error(f"删除报告文件失败 {report_file}: {str(e)}")
        else:
            # 处理单个文件
            try:
                if os.path.exists(report_pattern):
                    # 清空预警文件但保留文件本身
                    with open(report_pattern, 'w', encoding='utf-8') as f:
                        json.dump([], f, ensure_ascii=False, indent=2)
            except Exception as e:
                logging.error(f"清空报告文件失败 {report_pattern}: {str(e)}")
    
    # 不再需要清除缓存，因为get_latest_report函数不再使用lru_cache装饰器

if __name__ == '__main__':
    # 不自动打开浏览器
    app.run(debug=True, host='0.0.0.0', port=5000)