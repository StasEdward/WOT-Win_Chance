# -*- coding: utf-8 -*-
"""
Win Chance Mod - Рассчитывает и отображает шанс на победу
"""

import BigWorld
from Avatar import PlayerAvatar
from gui.battle_control import avatar_getter
import Account
import os
import math
import json
import codecs
import time

try:
    import cPickle as pickle
except ImportError:
    import pickle

import urllib2
import socket

# Глобальный конфиг API
API_CONFIG = {
    'enabled': True,
    'api_url': 'http://localhost:5000',
    'token': None,
    'account_id': None,
    'nickname': None,
    'region': 'RU'
}

def get_player_info():
    """Получает информацию об игроке"""
    try:
        player = BigWorld.player()
        if player and hasattr(player, 'databaseID'):
            account_id = player.databaseID
            nickname = getattr(player, 'name', 'Unknown')
            
            # Определяем регион по серверу
            from constants import AUTH_REALM
            region_map = {
                'RU': 'RU',
                'EU': 'EU',
                'NA': 'NA',
                'ASIA': 'ASIA'
            }
            region = region_map.get(AUTH_REALM, 'RU')
            
            return {
                'account_id': account_id,
                'nickname': nickname,
                'region': region
            }
    except Exception as e:
        debug("[WinChance] Error getting player info: {}".format(e))
    
    return None

def register_in_api():
    """
    Автоматически регистрирует мод в API и получает токен
    
    Returns:
        str: Токен или None при ошибке
    """
    try:
        # Получаем информацию об игроке
        player_info = get_player_info()
        if not player_info:
            log("[WinChance] Player info not yet available (normal in hangar)")
            return None
        
        url = "{}/api/auth/register".format(API_CONFIG['api_url'])
        
        # Данные для регистрации
        register_data = {
            'accountId': player_info['account_id'],
            'nickname': player_info['nickname'],
            'region': player_info['region']
        }
        
        log("[WinChance] Registering in API: {}@{}".format(
            player_info['nickname'], player_info['region']))
        
        # Отправляем запрос
        request = urllib2.Request(url)
        request.add_header('Content-Type', 'application/json; charset=utf-8')
        data = json.dumps(register_data, ensure_ascii=False).encode('utf-8')
        
        response = urllib2.urlopen(request, data, timeout=10)
        response_data = json.loads(response.read())
        
        token = response_data.get('token')
        
        if token:
            log("[WinChance] Registration successful! Token received.")
            
            # Обновляем конфиг
            API_CONFIG['token'] = token
            API_CONFIG['account_id'] = player_info['account_id']
            API_CONFIG['nickname'] = player_info['nickname']
            API_CONFIG['region'] = player_info['region']
            
            # Сохраняем конфиг
            save_api_config()
            
            return token
        else:
            err("[WinChance] Registration failed: no token in response")
            return None
            
    except urllib2.HTTPError as e:
        err("[WinChance] HTTP Error during registration: {} - {}".format(e.code, e.read()))
        return None
    except urllib2.URLError as e:
        err("[WinChance] URL Error during registration: {}".format(e.reason))
        return None
    except Exception as e:
        err("[WinChance] Error during registration: {}".format(e))
        import traceback
        err(traceback.format_exc())
        return None

def save_api_config():
    """Сохраняет конфигурацию API"""
    log("[WinChance] Saving API config")
    try:
        config_path = './mods/configs/mod_winchance_api.json'
        
        # Создаем директорию если не существует
        config_dir = os.path.dirname(config_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        with codecs.open(config_path, 'w', 'utf-8-sig') as f:
            json.dump(API_CONFIG, f, indent=2, ensure_ascii=False)
        
        log("[WinChance] API config saved")
        return True
        
    except Exception as e:
        err("[WinChance] Error saving API config: {}".format(e))
        return False

def check_and_register_if_needed():
    """
    Проверяет наличие токена и регистрируется если нужно
    
    Returns:
        bool: True если токен есть или получен успешно
    """
    try:
        # Если интеграция отключена - не регистрируемся
        if not API_CONFIG['enabled']:
            log("[WinChance] API integration is disabled in config")
            return False
        
        # Проверяем наличие токена
        if API_CONFIG.get('token'):
            log("[WinChance] Token found in config")
            return True
        
        log("[WinChance] No token found, attempting automatic registration...")
        
        # Пытаемся зарегистрироваться
        token = register_in_api()
        
        if token:
            log("[WinChance] Automatic registration successful!")
            return True
        else:
            log("[WinChance] Registration postponed (will retry when entering battle)")
            return False
            
    except Exception as e:
        err("[WinChance] Error in check_and_register_if_needed: {}".format(e))
        return False

def test_api_connection():
    """Тестирует подключение к API"""
    try:
        url = "{}/health".format(API_CONFIG['api_url'])
        response = urllib2.urlopen(url, timeout=5)
        
        if response.code == 200:
            log("[WinChance] API connection test successful")
            return True
        else:
            err("[WinChance] API returned status: {}".format(response.code))
            return False
            
    except Exception as e:
        err("[WinChance] API connection test failed: {}".format(e))
        return False

def load_api_config():
    """Загружает конфигурацию API"""
    global API_CONFIG
    try:
        config_path = './mods/configs/mod_winchance_api.json'
        
        # Создаем директорию если не существует
        config_dir = os.path.dirname(config_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        if os.path.exists(config_path):
            with codecs.open(config_path, 'r', 'utf-8-sig') as f:
                config = json.load(f)
                API_CONFIG.update(config)
                log("[WinChance] API config loaded: enabled={}, url={}".format(
                    API_CONFIG['enabled'], API_CONFIG['api_url']))
        else:
            log("[WinChance] API config not found, creating default")
            save_api_config()
            
    except Exception as e:
        err("[WinChance] Error loading API config: {}".format(e))

def send_battle_to_api(battle_data):
    """
    Отправляет результат боя в API
    
    Args:
        battle_data: Словарь с данными боя
    """
    if not API_CONFIG['enabled']:
        log("[WinChance] API integration disabled")
        return False
    
    if not API_CONFIG['token']:
        log("[WinChance] API token not configured")
        return False
    
    try:
        url = "{}/api/battles".format(API_CONFIG['api_url'])
        
        # Формируем данные для API (без обертки, контроллер ожидает прямой объект)
        api_data = json.dumps(battle_data, ensure_ascii=False).encode('utf-8')
        
        # Логируем полный JSON для отладки (с отступами для читаемости)
        log("[WinChance] Sending JSON to API:")
        log(json.dumps(battle_data, indent=2, ensure_ascii=False))
        
        # Создаем request
        request = urllib2.Request(url)
        request.add_header('Content-Type', 'application/json; charset=utf-8')
        request.add_header('Authorization', 'Bearer {}'.format(API_CONFIG['token']))
        
        # Отправляем с таймаутом
        response = urllib2.urlopen(request, api_data, timeout=5)
        response_data = response.read()
        
        log("[WinChance] Battle sent to API successfully: {}".format(response_data))
        return True
        
    except urllib2.HTTPError as e:
        error_body = e.read()
        err("[WinChance] HTTP Error sending to API: {} - {}".format(e.code, error_body))
        # Логируем детали для диагностики
        if e.code == 409:
            err("[WinChance] Conflict: ArenaUniqueId already exists. This battle was already recorded.")
        return False
    except urllib2.URLError as e:
        err("[WinChance] URL Error sending to API: {}".format(e.reason))
        return False
    except socket.timeout:
        err("[WinChance] Timeout sending to API")
        return False
    except Exception as e:
        err("[WinChance] Error sending to API: {}".format(e))
        import traceback
        err(traceback.format_exc())
        return False

# XVM imports
try:
    # XVM v13 uses openwg_libraries and openwg_packages structure
    from xfw.logger import *
    from xfw.events import registerEvent
    try:
        from xfw import as_event
    except ImportError:
        # as_event might not be available in all XFW versions
        def as_event(event_name, data):
            debug("[WinChance] as_event called but not available: {}".format(event_name))
    
    import xvm_battle.battle as battle
    XVM_AVAILABLE = True
    log("[WinChance] XVM modules loaded successfully")
    
    # Try to import statistics - may not be available in all XVM versions
    try:
        import xvm_statistics.statisticsengine as statisticsengine
    except ImportError:
        statisticsengine = None
        debug("[WinChance] XVM statistics module not available")
        
except ImportError as e:
    print("[WinChance] XVM import error: {}".format(e))
    XVM_AVAILABLE = False
    statisticsengine = None
    
    # Fallback logging functions when XVM is not available
    def log(msg):
        print(msg)
    
    def err(msg):
        print("ERROR: {}".format(msg))
    
    def debug(msg):
        print("DEBUG: {}".format(msg))
    
    # Fallback for XVM event functions
    def as_event(event_name, data):
        debug("[WinChance] as_event called (XVM not available): {}".format(event_name))
    
    def registerEvent(module, event_type, callback):
        debug("[WinChance] registerEvent called (XVM not available): {}.{}".format(module, event_type))


def get_current_time():
    """Получает текущее время в формате строки"""
    try:
        # Используем time.localtime вместо datetime для совместимости с WoT
        current_time = time.localtime()
        # ISO 8601 формат для совместимости с .NET DateTime
        return time.strftime('%Y-%m-%dT%H:%M:%S', current_time)
    except:
        # Fallback на BigWorld time
        return str(int(BigWorld.time()))



class WinChanceCalculator(object):
    """Калькулятор шанса на победу"""
    
    def __init__(self):
        self.ally_wgr = 0
        self.enemy_wgr = 0
        self.win_chance = 50.0
        self.player_team = 1
        
    def calculate_team_wgr(self, players_data, team):
        """
        Рассчитывает средний WGR команды
        
        Args:
            players_data: Данные игроков из XVM
            team: Номер команды (1 или 2)
            
        Returns:
            float: Средний WGR команды
        """
        wgr_values = []
        
        for vehicle_id, data in players_data.items():
            if data.get('team') != team:
                continue
                
            # Получаем статистику игрока
            stats = data.get('stats', {})
            
            # WGR (Wargaming Rating) - комплексный рейтинг
            wgr = stats.get('wgr', None)
            
            if wgr is not None and wgr > 0:
                wgr_values.append(wgr)
            else:
                # Если WGR недоступен, используем альтернативный расчет
                # на основе винрейта и количества боев
                wins = stats.get('wins', 0)
                battles = stats.get('battles', 0)
                
                if battles > 0:
                    winrate = (wins / float(battles)) * 100
                    # Простая оценка WGR на основе винрейта
                    estimated_wgr = self._estimate_wgr_from_winrate(winrate, battles)
                    wgr_values.append(estimated_wgr)
        
        # Возвращаем средний WGR
        if wgr_values:
            return sum(wgr_values) / len(wgr_values)
        return 5000  # Дефолтное значение (средний игрок)
    
    def _estimate_wgr_from_winrate(self, winrate, battles):
        """
        Оценивает WGR на основе винрейта
        
        Args:
            winrate: Процент побед
            battles: Количество боев
            
        Returns:
            float: Оценочный WGR
        """
        # Базовый расчет: WGR примерно коррелирует с винрейтом
        # WGR 5000 = ~50% WR, каждый 1% WR ≈ 150-200 WGR
        base_wgr = 5000
        wr_delta = winrate - 50.0
        wgr = base_wgr + (wr_delta * 175)
        
        # Корректировка на основе количества боев
        # Игроки с малым количеством боев менее надежны
        if battles < 100:
            # Регрессия к среднему
            confidence = battles / 100.0
            wgr = base_wgr + (wgr - base_wgr) * confidence
        
        # Ограничиваем диапазон
        wgr = max(0, min(15000, wgr))
        
        return wgr
    
    def calculate_win_chance(self, ally_wgr, enemy_wgr):
        """
        Рассчитывает шанс на победу на основе разницы WGR
        
        Args:
            ally_wgr: Средний WGR союзной команды
            enemy_wgr: Средний WGR вражеской команды
            
        Returns:
            float: Шанс на победу (0-100%)
        """
        # Разница в рейтингах
        wgr_diff = ally_wgr - enemy_wgr
        
        # Используем логистическую функцию для расчета вероятности
        # Это дает плавную S-образную кривую
        # Коэффициент 0.0005 подобран эмпирически
        # При разнице в 1000 WGR даст примерно 62% шанса
        k = 0.0005
        win_probability = 1.0 / (1.0 + math.exp(-k * wgr_diff))
        
        # Конвертируем в проценты
        win_chance = win_probability * 100.0
        
        # Ограничиваем диапазон 5-95% (никогда не бывает 100% уверенности)
        win_chance = max(5.0, min(95.0, win_chance))
        
        return win_chance
    
    def update(self, players_data, player_team):
        """
        Обновляет расчет шанса на победу
        
        Args:
            players_data: Данные игроков из XVM
            player_team: Команда игрока (1 или 2)
        """
        self.player_team = player_team
        
        # Рассчитываем WGR для обеих команд
        self.ally_wgr = self.calculate_team_wgr(players_data, player_team)
        enemy_team = 2 if player_team == 1 else 1
        self.enemy_wgr = self.calculate_team_wgr(players_data, enemy_team)
        
        # Рассчитываем шанс на победу
        self.win_chance = self.calculate_win_chance(self.ally_wgr, self.enemy_wgr)

class BattleStatsCollector(object):
    """Собирает детальную статистику боя"""
    
    def __init__(self):
        self.arena_id = None
        self.battle_start_time = None
        self.player_vehicle = None
        self.map_name = None
        self.battle_type = None
        self.player_team = None
        
        # Статистика
        self.damage_dealt = 0
        self.damage_assisted = 0
        self.damage_blocked = 0
        self.kills = 0
        self.spotted = 0
        self.shots = 0
        self.hits = 0
        self.penetrations = 0
        
    def on_battle_start(self):
        """Инициализация при старте боя"""
        try:
            player = BigWorld.player()
            arena = avatar_getter.getArena()
            
            if arena:
                self.arena_id = getattr(arena, 'arenaUniqueID', 0)
                self.battle_start_time = get_current_time()
                
                # Получаем информацию об арене
                arena_type = getattr(arena, 'arenaType', None)
                if arena_type:
                    self.map_name = getattr(arena_type, 'name', 'Unknown')
                    self.battle_type = getattr(arena_type, 'gameplayName', 'random')
                
                # Информация об игроке
                if hasattr(player, 'team'):
                    self.player_team = player.team
                
                # Информация о технике
                if hasattr(player, 'vehicleTypeDescriptor'):
                    vehicle_desc = player.vehicleTypeDescriptor
                    vehicle_type = getattr(vehicle_desc, 'type', None)
                    
                    # Extract vehicle information safely
                    vehicle_id = getattr(vehicle_type, 'compactDescr', 0) if vehicle_type else 0
                    vehicle_name = getattr(vehicle_type, 'userString', 'Unknown') if vehicle_type else 'Unknown'
                    
                    # tags is a frozenset, need to convert to list to access elements
                    vehicle_tags = getattr(vehicle_type, 'tags', frozenset()) if vehicle_type else frozenset()
                    if vehicle_tags:
                        # Convert frozenset to list and get first tag
                        tags_list = list(vehicle_tags)
                        # Look for vehicle class tag (heavyTank, mediumTank, etc.)
                        vehicle_type_class = 'unknown'
                        for tag in tags_list:
                            if 'Tank' in tag or 'SPG' in tag:
                                vehicle_type_class = tag
                                break
                        if vehicle_type_class == 'unknown' and tags_list:
                            vehicle_type_class = tags_list[0]
                    else:
                        vehicle_type_class = 'unknown'
                    
                    vehicle_name_parts = getattr(vehicle_type, 'name', '') if vehicle_type else ''
                    vehicle_nation = vehicle_name_parts.split(':')[0] if vehicle_name_parts and ':' in vehicle_name_parts else 'unknown'
                    
                    self.player_vehicle = {
                        'id': vehicle_id,
                        'name': vehicle_name,
                        'tier': getattr(vehicle_desc, 'level', 0),
                        'type': vehicle_type_class,
                        'nation': vehicle_nation
                    }
                    
            log("[WinChance] Battle stats collector initialized for arena {}".format(self.arena_id))
            
        except Exception as e:
            err("[WinChance] Error in BattleStatsCollector.on_battle_start: {}".format(e))
    
    def update_from_player_feedback(self, event_type, *args):
        """Обновляет статистику на основе событий игры"""
        try:
            if event_type == 'DAMAGE_DEALT':
                self.damage_dealt += args[0] if args else 0
            elif event_type == 'DAMAGE_ASSISTED':
                self.damage_assisted += args[0] if args else 0
            elif event_type == 'BLOCKED_DAMAGE':
                self.damage_blocked += args[0] if args else 0
            elif event_type == 'VEHICLE_KILLED':
                self.kills += 1
            elif event_type == 'VEHICLE_SPOTTED':
                self.spotted += 1
            elif event_type == 'SHOT_FIRED':
                self.shots += 1
            elif event_type == 'SHOT_HIT':
                self.hits += 1
            elif event_type == 'SHOT_PENETRATED':
                self.penetrations += 1
                
        except Exception as e:
            err("[WinChance] Error updating battle stats: {}".format(e))
    
    def prepare_api_data(self, battle_result, win_chance=0.0, ally_wgr=0, enemy_wgr=0):
        """
        Подготавливает данные для отправки в API
        
        Args:
            battle_result: Результат боя ('win', 'lose', 'draw')
            win_chance: Шанс на победу (0.0-100.0)
            ally_wgr: Рейтинг союзников
            enemy_wgr: Рейтинг противников
            
        Returns:
            dict: Данные в формате API (PascalCase для .NET)
        """
        try:
            if not self.arena_id:
                err("[WinChance] Cannot prepare API data - arena_id is not set")
                return None
            
            if not self.player_vehicle:
                err("[WinChance] Cannot prepare API data - player_vehicle is not set")
                return None
            
            log("[WinChance] Preparing API data: arena_id={}, result={}".format(
                self.arena_id, battle_result))
            
            # Формат данных согласно C# BattleResultDto (PascalCase)
            return {
                'ArenaUniqueId': self.arena_id or 0,
                'BattleTime': self.battle_start_time or get_current_time(),
                'MapName': self.map_name or 'Unknown',
                'BattleType': self.battle_type or 'random',
                'Team': self.player_team or 1,
                'Result': battle_result,               
                'DamageDealt': self.damage_dealt,
                'DamageAssisted': self.damage_assisted,
                'DamageBlocked': self.damage_blocked,
                'Kills': self.kills,
                'Spotted': self.spotted,
                'Experience': 0,  # Будет обновлено из результатов боя
                'Credits': 0,  # Будет обновлено из результатов боя
                'Shots': self.shots,
                'Hits': self.hits,
                'Penetrations': self.penetrations,
                'WinChance': win_chance,
                'AllyWgr': ally_wgr,
                'EnemyWgr': enemy_wgr,
                
                # TankInfoDto (PascalCase)
                'Tank': {
                    'TankId': self.player_vehicle.get('id', 0) if self.player_vehicle else 0,
                    'Name': self.player_vehicle.get('name', 'Unknown') if self.player_vehicle else 'Unknown',
                    'Tier': self.player_vehicle.get('tier', 0) if self.player_vehicle else 0,
                    'Type': self.player_vehicle.get('type', 'unknown') if self.player_vehicle else 'unknown',
                    'Nation': self.player_vehicle.get('nation', 'unknown') if self.player_vehicle else 'unknown'
                }
            }
        except Exception as e:
            err("[WinChance] Error preparing API data: {}".format(e))
            import traceback
            err(traceback.format_exc())
            return None



class DraggableWinChanceWindow(object):
    """Перетаскиваемое окно для отображения Win Chance"""
    
    def __init__(self):
        self.components = []
        self.isDragging = False
        self.lastMousePos = (0, 0)
        self.mouseHandlerActive = False
        self.callbackID = None
        
        # Дефолтная позиция (правый верхний угол)
        self.posX = 0.75
        self.posY = 0.05
        
        self.loadConfig()
    
    def loadConfig(self):
        """Загружает позицию из конфига"""
        try:
            config_path = './mods/configs/mod_winchance.json'
            if os.path.exists(config_path):
                import json
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.posX = config.get('posX', self.posX)
                    self.posY = config.get('posY', self.posY)
                    log("[WinChance] Config loaded: position ({:.3f}, {:.3f})".format(self.posX, self.posY))
        except Exception as e:
            debug("[WinChance] Error loading config: {}".format(e))
    
    def saveConfig(self):
        """Сохраняет позицию в конфиг"""
        try:
            import json
            config_path = './mods/configs/mod_winchance.json'
            config_dir = os.path.dirname(config_path)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            
            config = {
                'posX': self.posX,
                'posY': self.posY
            }
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            log("[WinChance] Config saved: position ({:.3f}, {:.3f})".format(self.posX, self.posY))
        except Exception as e:
            debug("[WinChance] Error saving config: {}".format(e))
    
    def create(self):
        """Cоздает окно"""
        try:
            log("[WinChance] Window created (GUI-based)")
            return True
        except Exception as e:
            err("[WinChance] Error creating window: {}".format(e))
            return False
    
    def update_text(self, text):
        """Обновляет текст окна"""
        try:
            self.createWindow(text)
        except Exception as e:
            debug("[WinChance] Update text error: {}".format(e))
    
    def createWindow(self, message):
        """Создает/обновляет окно с текстом"""
        try:
            self.destroyWindow()
            
            import GUI
            
            # Парсим сообщение: "Win Chance: 56.5% | Ally WGR: 5684 | Enemy WGR: 5160"
            parts = message.split('|')
            
            # === ФОН ===
            bgLines = 3
            for i in range(bgLines):
                bgLine = GUI.Text(u"█" * 50)
                bgLine.font = "default_small.font"
                bgLine.colour = (240, 240, 240, 230)  # Светло-серый фон
                bgLine.position = (self.posX - 0.01, self.posY + i * 0.030, 0.9)
                GUI.addRoot(bgLine)
                self.components.append(('bg', bgLine, i))
            
            
            # === Win Chance (первая строка, сверху) ===
            if len(parts) > 0:
                chance_text = parts[0].strip()  # "Win Chance: 56.5%"
                chance_value = float(chance_text.split(':')[1].strip().replace('%', ''))
                
                # Цвет на основе шанса
                if chance_value >= 60:
                    color = (50, 205, 50, 255)  # Зеленый
                elif chance_value >= 45:
                    color = (255, 215, 0, 255)  # Желтый/золотой
                else:
                    color = (220, 20, 60, 255)  # Красный
                
                chanceComp = GUI.Text(chance_text)
                chanceComp.font = "default_medium.font"
                chanceComp.colour = color
                chanceComp.position = (self.posX, self.posY + 0.040, 0.95)  # Больший Y = выше
                GUI.addRoot(chanceComp)
                self.components.append(('text', chanceComp, 0.040))
            
            # === WGR (вторая строка, снизу) ===
            if len(parts) >= 3:
                # Форматируем: "Ally WGR: 5580 | Enemy WGR: 4463"
                ally_wgr = parts[1].strip().replace('Ally WGR:', '').strip()
                enemy_wgr = parts[2].strip().replace('Enemy WGR:', '').strip()
                
                wgr_line = u"Ally WGR: {} | Enemy WGR: {}".format(ally_wgr, enemy_wgr)
                
                wgrText = GUI.Text(wgr_line)
                wgrText.font = "default_small.font"
                wgrText.colour = (120, 120, 120, 255)  # Серый
                wgrText.position = (self.posX, self.posY + 0.008, 0.95)  # Меньший Y = ниже
                GUI.addRoot(wgrText)
                self.components.append(('text', wgrText, 0.008))
            
            self.startMouseHandler()
            
        except Exception as e:
            err("[WinChance] Error creating window: {}".format(e))
    
    def destroyWindow(self):
        """Уничтожает окно"""
        try:
            import GUI
            self.stopMouseHandler()
            for _, component, _ in self.components:
                try:
                    GUI.delRoot(component)
                except:
                    pass
            self.components = []
        except:
            pass
    
    def startMouseHandler(self):
        """Запускает обработчик мыши для перетаскивания"""
        if not self.mouseHandlerActive:
            self.mouseHandlerActive = True
            self.checkMouseInput()
    
    def stopMouseHandler(self):
        """Останавливает обработчик мыши"""
        self.mouseHandlerActive = False
        if self.callbackID is not None:
            try:
                BigWorld.cancelCallback(self.callbackID)
            except:
                pass
            self.callbackID = None
    
    def checkMouseInput(self):
        """Проверяет ввод мыши для перетаскивания (Ctrl + ЛКМ)"""
        if not self.mouseHandlerActive:
            return
        
        try:
            import GUI
            import Keys
            
            cursor = GUI.mcursor()
            if cursor:
                mouseX, mouseY = cursor.position[0], cursor.position[1]
                
                # Проверяем Ctrl + ЛКМ
                ctrlPressed = BigWorld.isKeyDown(Keys.KEY_LCONTROL) or BigWorld.isKeyDown(Keys.KEY_RCONTROL)
                leftMouseDown = BigWorld.isKeyDown(Keys.KEY_LEFTMOUSE)
                
                if ctrlPressed and leftMouseDown:
                    if not self.isDragging:
                        self.isDragging = True
                        self.lastMousePos = (mouseX, mouseY)
                    else:
                        deltaX = mouseX - self.lastMousePos[0]
                        deltaY = mouseY - self.lastMousePos[1]
                        
                        self.posX += deltaX
                        self.posY += deltaY
                        self.updateWindowPosition()
                        self.lastMousePos = (mouseX, mouseY)
                else:
                    if self.isDragging:
                        self.isDragging = False
                        self.saveConfig()
        except Exception as e:
            debug("[WinChance] Mouse error: {}".format(e))
        
        # Следующая проверка
        self.callbackID = BigWorld.callback(0.05, self.checkMouseInput)
    
    def updateWindowPosition(self):
        """Обновляет позицию всех компонентов"""
        try:
            import GUI
            for comp_type, component, offset in self.components:
                if comp_type == 'bg':
                    component.position = (self.posX - 0.01, self.posY + offset * 0.022, 0.9)
                elif comp_type == 'text':
                    component.position = (self.posX, self.posY + offset, 0.95)
        except:
            pass
    
    def destroy(self):
        """Уничтожает окно"""
        try:
            self.destroyWindow()
            log("[WinChance] Window destroyed")
        except Exception as e:
            err("[WinChance] Error destroying window: {}".format(e))


class BattleResultLogger(object):
    """Класс для логирования фактических результатов боев"""
    
    def __init__(self):
        self.log_dir = './mods/configs/mod_winchance/logs'
        self.results_file = os.path.join(self.log_dir, 'battle_results.csv')
        self.results_json = os.path.join(self.log_dir, 'battle_results.json')
        self.pending_file = os.path.join(self.log_dir, 'pending_battles.json')
        self.ensure_log_directory()
        
        # Храним данные ожидающих боев: {arena_id: battle_data}
        self.pending_battles = {}
        self._load_pending_battles()
        
    def ensure_log_directory(self):
        """Создает директорию для логов если её нет"""
        try:
            if not os.path.exists(self.log_dir):
                os.makedirs(self.log_dir)
                log("[WinChance] Created results log directory: {}".format(self.log_dir))
        except Exception as e:
            err("[WinChance] Error creating results log directory: {}".format(e))

    def _load_pending_battles(self):
        """Загружает список ожидающих боев из файла"""
        try:
            if os.path.exists(self.pending_file):
                with open(self.pending_file, 'r') as f:
                    content = f.read()
                    if content:
                        self.pending_battles = json.loads(content)
                        log("[WinChance] Loaded {} pending battles from storage".format(len(self.pending_battles)))
            else:
                self.pending_battles = {}
        except Exception as e:
            err("[WinChance] Error loading pending battles: {}".format(e))
            self.pending_battles = {}

    def _save_pending_battles_to_file(self):
        """Сохраняет список ожидающих боев в файл"""
        try:
            with open(self.pending_file, 'w') as f:
                json.dump(self.pending_battles, f, indent=2)
        except Exception as e:
            err("[WinChance] Error saving pending battles: {}".format(e))

    def save_prediction(self, battle_data):
        """
        Сохраняет предсказание для текущего боя
        
        Args:
            battle_data: Данные боя с предсказанием
        """
        try:
            arena_id = str(battle_data.get('arenaUniqueId', battle_data.get('arena_id', '')))
            if not arena_id:
                return

            self.pending_battles[arena_id] = battle_data.copy()
            self._save_pending_battles_to_file()
            
            log("[WinChance] Prediction saved for battle {} (Total pending: {})".format(
                arena_id, len(self.pending_battles)))
        except Exception as e:
            err("[WinChance] Error saving prediction: {}".format(e))

    def get_pending_battle(self, arena_id):
        """Возвращает данные ожидающего боя по ID"""
        return self.pending_battles.get(str(arena_id))

    def remove_pending_battle(self, arena_id):
        """Удаляет бой из списка ожидающих"""
        if str(arena_id) in self.pending_battles:
            del self.pending_battles[str(arena_id)]
            self._save_pending_battles_to_file()
    
    def save_result(self, battle_id, win, team_result, personal_result):
        """
        Сохраняет фактический результат боя
        
        Args:
            battle_id: ID боя
            win: True если победа, False если поражение
            team_result: Результат команды (1=победа, 2=поражение, 0=ничья)
            personal_result: Личный результат игрока
        """
        try:
            pending_battle = self.get_pending_battle(battle_id)
            if pending_battle is None:
                log("[WinChance] No pending battle data found for result logging (ID: {})".format(battle_id))
                return
            
            # Время окончания боя
            end_time = get_current_time()
            
            # Формируем полные данные результата
            result_data = pending_battle.copy()
            result_data['end_time'] = end_time
            result_data['victory'] = win
            result_data['team_result'] = team_result
            result_data['personal_result'] = personal_result
            
            # Рассчитываем точность предсказания
            predicted_win = result_data.get('win_chance', 50) >= 50
            result_data['prediction_correct'] = (predicted_win == win)
            result_data['prediction_error'] = abs(result_data.get('win_chance', 50) - (100 if win else 0))
            
            # Сохраняем в CSV
            self._save_result_to_csv(result_data)
            
            # Сохраняем в JSON
            self._save_result_to_json(result_data)
            
            log("[WinChance] Battle result saved: Battle ID={}, Victory={}, Predicted={:.1f}%".format(
                battle_id, win, result_data.get('win_chance', 0)))
            
            # Удаляем из ожидающих
            self.remove_pending_battle(battle_id)
            
        except Exception as e:
            err("[WinChance] Error saving battle result: {}".format(e))
            import traceback
            err(traceback.format_exc())
    
    def _save_result_to_csv(self, result_data):
        """Сохраняет результат в CSV файл"""
        try:
            file_exists = os.path.exists(self.results_file)
            
            with codecs.open(self.results_file, 'a', encoding='utf-8') as f:
                # Заголовок
                if not file_exists:
                    f.write('Battle_ID,Start_Time,End_Time,Player_Name,Vehicle_Name,'
                           'Win_Chance,Ally_WGR,Enemy_WGR,Victory,Team_Result,'
                           'Prediction_Correct,Prediction_Error\n')
                
                # Данные
                line = '{},{},{},{},{},{:.1f},{:.0f},{:.0f},{},{},{},{:.1f}\n'.format(
                    result_data.get('battle_id', ''),
                    result_data.get('start_time', ''),
                    result_data.get('end_time', ''),
                    result_data.get('player_name', ''),
                    result_data.get('player_vehicle_name', ''),
                    result_data.get('win_chance', 0),
                    result_data.get('ally_wgr', 0),
                    result_data.get('enemy_wgr', 0),
                    'Win' if result_data.get('victory', False) else 'Loss',
                    result_data.get('team_result', 0),
                    'Yes' if result_data.get('prediction_correct', False) else 'No',
                    result_data.get('prediction_error', 0)
                )
                f.write(line)
            
            debug("[WinChance] Result logged to CSV: {}".format(self.results_file))
            
        except Exception as e:
            err("[WinChance] Error writing result to CSV: {}".format(e))
    
    def _save_result_to_json(self, result_data):
        """Сохраняет результат в JSON файл"""
        try:
            # Загружаем существующие данные
            results = []
            if os.path.exists(self.results_json):
                try:
                    with codecs.open(self.results_json, 'r', encoding='utf-8') as f:
                        results = json.load(f)
                except:
                    results = []
            
            # Добавляем новый результат
            results.append(result_data)
            
            # Сохраняем обратно
            with codecs.open(self.results_json, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            debug("[WinChance] Result logged to JSON: {}".format(self.results_json))
            
        except Exception as e:
            err("[WinChance] Error writing result to JSON: {}".format(e))


class BattleLogger(object):
    """Класс для логирования результатов боев"""
    
    def __init__(self):
        self.log_dir = './mods/configs/mod_winchance/logs'
        self.ensure_log_directory()
        
    def ensure_log_directory(self):
        """Создает директорию для логов если её нет"""
        try:
            if not os.path.exists(self.log_dir):
                os.makedirs(self.log_dir)
                log("[WinChance] Created log directory: {}".format(self.log_dir))
        except Exception as e:
            err("[WinChance] Error creating log directory: {}".format(e))
    
    def log_battle_result(self, battle_data):
        """
        Записывает результаты боя в файл
        
        Args:
            battle_data: Словарь с данными боя
                - battle_id: ID боя
                - start_time: Время начала боя
                - player_vehicle_id: ID танка игрока
                - player_vehicle_name: Название танка игрока
                - player_name: Имя игрока
                - win_chance: Шанс на победу (%)
                - ally_wgr: WGR союзников
                - enemy_wgr: WGR противников
        """
        try:
            # Записываем в JSON файл (один файл на день)
            self._log_to_json(battle_data)
            
            # Также записываем в CSV для удобства анализа
            self._log_to_csv(battle_data)
            
            log("[WinChance] Battle result logged: Battle ID={}, Win Chance={:.1f}%".format(
                battle_data.get('battle_id', 'Unknown'),
                battle_data.get('win_chance', 0)))
            
        except Exception as e:
            err("[WinChance] Error logging battle result: {}".format(e))
            import traceback
            err(traceback.format_exc())
    
    def _log_to_json(self, battle_data):
        """Записывает данные в JSON файл"""
        try:
            # Имя файла на основе даты
            date_str = time.strftime('%Y-%m-%d', time.localtime())
            json_file = os.path.join(self.log_dir, 'battles_{}.json'.format(date_str))
            
            # Загружаем существующие данные или создаем новый список
            battles = []
            if os.path.exists(json_file):
                try:
                    with codecs.open(json_file, 'r', encoding='utf-8') as f:
                        battles = json.load(f)
                except:
                    battles = []
            
            # Добавляем новую запись
            battles.append(battle_data)
            
            # Сохраняем обратно
            with codecs.open(json_file, 'w', encoding='utf-8') as f:
                json.dump(battles, f, ensure_ascii=False, indent=2)
            
            debug("[WinChance] Logged to JSON: {}".format(json_file))
            
        except Exception as e:
            err("[WinChance] Error writing to JSON: {}".format(e))
    
    def _log_to_csv(self, battle_data):
        """Записывает данные в CSV файл"""
        try:
            csv_file = os.path.join(self.log_dir, 'battles.csv')
            
            # Проверяем, существует ли файл (для заголовков)
            file_exists = os.path.exists(csv_file)
            
            with codecs.open(csv_file, 'a', encoding='utf-8') as f:
                # Записываем заголовок если файл новый
                if not file_exists:
                    f.write('Battle_ID,Start_Time,Player_Name,Vehicle_ID,Vehicle_Name,Win_Chance,Ally_WGR,Enemy_WGR\n')
                
                # Записываем данные
                line = '{},{},{},{},{},{:.1f},{:.0f},{:.0f}\n'.format(
                    battle_data.get('battle_id', ''),
                    battle_data.get('start_time', ''),
                    battle_data.get('player_name', ''),
                    battle_data.get('player_vehicle_id', ''),
                    battle_data.get('player_vehicle_name', ''),
                    battle_data.get('win_chance', 0),
                    battle_data.get('ally_wgr', 0),
                    battle_data.get('enemy_wgr', 0)
                )
                f.write(line)
            
            debug("[WinChance] Logged to CSV: {}".format(csv_file))
            
        except Exception as e:
            err("[WinChance] Error writing to CSV: {}".format(e))


class WinChanceDisplay(object):
    """Класс для отображения шанса на победу"""
    
    def __init__(self):
        self.calculator = WinChanceCalculator()
        self.is_in_battle = False
        self.overlay = DraggableWinChanceWindow()
        self.data_ready = False
        self.logger = BattleLogger()
        self.result_logger = BattleResultLogger()
        
        # Данные текущего боя для логирования
        self.current_battle_data = None
        
        # Сохраняем данные арены для использования после окончания боя
        self.saved_battle_id = None
        self.saved_player_team = None
        self.saved_arena_period_callback = None
        self.monitoring_active = False  # Флаг активного мониторинга
        
        # Подписываемся на события результатов боя
        self._subscribe_to_battle_events()
        self.stats_collector = BattleStatsCollector()
        
    def on_battle_start(self):
        """Вызывается при старте боя"""

        """Обработчик начала боя"""
        try:
            log("[WinChance] Battle started")
            self.is_in_battle = True
            
            # Если токена нет - пытаемся зарегистрироваться снова
            if API_CONFIG['enabled'] and not API_CONFIG.get('token'):
                log("[WinChance] Attempting registration at battle start...")
                check_and_register_if_needed()
        
        except Exception as e:
            err("[WinChance] Error in on_battle_start: {}".format(e))
            import traceback
            err(traceback.format_exc())
        
        try:
            # Если есть активный мониторинг предыдущего боя
            if self.monitoring_active and self.saved_arena_period_callback is not None:
                log("[WinChance] Previous battle monitoring is still active, attempting to save results...")
                
                # Пытаемся получить результаты предыдущего боя
                try:
                    arena = avatar_getter.getArena()
                    if arena is not None:
                        # Арена еще есть, пробуем получить результаты
                        period = getattr(arena, 'period', None)
                        if period == 3:
                            log("[WinChance] Previous battle finished, saving results before new battle")
                            self._try_get_battle_results_from_arena(arena)
                        else:
                            log("[WinChance] Previous battle still in progress (period={}), cannot save results".format(period))
                except Exception as e:
                    err("[WinChance] Error checking previous battle: {}".format(e))
                
                # Останавливаем старый мониторинг
                try:
                    BigWorld.cancelCallback(self.saved_arena_period_callback)
                except:
                    pass
                self.saved_arena_period_callback = None
                self.monitoring_active = False
                log("[WinChance] Previous battle monitoring stopped")
            
            self.is_in_battle = True
            self.data_ready = False
            self.current_battle_data = None
            log("[WinChance] Battle started, waiting for XVM data...")
            
            # Собираем базовую информацию о бое
            self._collect_battle_info()
            
            # Создаем overlay (но не показываем пока нет данных)
            self.overlay.create()
            
            # Даем XVM время загрузить данные, затем рассчитываем один раз
            BigWorld.callback(3.0, self._calculate_once)
            
            # Инициализируем сбор статистики
            self.stats_collector.on_battle_start()
            
        except Exception as e:
            err("[WinChance] Error in on_battle_start: {}".format(e))
    
    def on_battle_end(self):
        """Вызывается при окончании боя"""
        try:
            log("[WinChance] Battle ended (player left)")
            
            # НЕ отменяем callback - продолжаем мониторинг арены
            # до получения результатов боя
            # Callback отменится автоматически когда arena станет None
            
            self.is_in_battle = False
            self.data_ready = False
            
            # Уничтожаем overlay
            self.overlay.destroy()
            
            log("[WinChance] Overlay destroyed, arena monitoring continues")
            
        except Exception as e:
            err("[WinChance] Error in on_battle_end: {}".format(e))
    
    
    def _calculate_once(self):
        """Рассчитывает win chance один раз когда данные готовы"""
        try:
            if not self.is_in_battle:
                return
            
            # Если данные уже обработаны - не повторяем
            if self.data_ready:
                return
            
            # Счетчик попыток
            if not hasattr(self, '_calc_retries'):
                self._calc_retries = 0
            self._calc_retries += 1
            
            log("[WinChance] Calculating win chance (attempt {})...".format(self._calc_retries))
            
            # Получаем данные игроков
            arena = avatar_getter.getArena()
            if arena is None:
                if self._calc_retries < 15:
                    BigWorld.callback(2.0, self._calculate_once)
                return
            
            # Получаем команду игрока
            player = BigWorld.player()
            if not hasattr(player, 'team'):
                if self._calc_retries < 15:
                    BigWorld.callback(2.0, self._calculate_once)
                return
            
            player_team = player.team
            
            # Получаем данные из XVM
            players_data = self._get_players_data()
            if not players_data:
                if self._calc_retries < 15:
                    BigWorld.callback(2.0, self._calculate_once)
                return
            
            # Проверяем что получили реальные данные XVM (не дефолтные)
            real_data_count = 0
            for vehicle_id, data in players_data.items():
                stats = data.get('stats', {})
                wgr = stats.get('wgr', 0)
                if wgr > 0 and wgr != 5000:  # Не дефолтное значение
                    real_data_count += 1
            
            log("[WinChance] Got {} players with real XVM data".format(real_data_count))
            
            # Если меньше 20 игроков с реальными данными - ждем еще, но не вечно
            # Максимум 30 секунд (15 попыток * 2 сек)
            if real_data_count < 20 and self._calc_retries < 15:
                debug("[WinChance] Waiting for more XVM data ({}/20), retrying in 2 sec...".format(real_data_count))
                BigWorld.callback(2.0, self._calculate_once)
                return
            
            if real_data_count < 20:
                log("[WinChance] Timeout waiting for full data. Calculating with partial data ({} players)".format(real_data_count))
            else:
                log("[WinChance] XVM data ready, calculating...")
                
            # Данные готовы (или таймаут)! Рассчитываем
            self.calculator.update(players_data, player_team)
            
            # Отображаем результаты
            self._show_display()
            self.data_ready = True
            
            # Сохраняем результаты в лог файл
            self._save_battle_results()
            
            # Сохраняем данные для получения результатов после боя
            self._save_arena_data_for_results()
            
            # Отправляем предварительные данные в API со статусом "undone"
            if API_CONFIG['enabled'] and API_CONFIG.get('token'):
                try:
                    log("[WinChance] Sending initial prediction to API (undone status)...")
                    undone_data = self.stats_collector.prepare_api_data(
                        battle_result='undone',
                        win_chance=self.calculator.win_chance,
                        ally_wgr=self.calculator.ally_wgr,
                        enemy_wgr=self.calculator.enemy_wgr
                    )
                    if undone_data:
                        send_battle_to_api(undone_data)
                except Exception as e:
                    err("[WinChance] Error sending initial prediction: {}".format(e))
            
            log("[WinChance] Win chance displayed successfully")
            
        except Exception as e:
            err("[WinChance] Error in _calculate_once: {}".format(e))
            import traceback
            err(traceback.format_exc())
    
    def _get_players_data(self):
        """
        Получает данные игроков из XVM
        
        Returns:
            dict: Данные игроков
        """
        try:
            players_data = {}
            
            arena = avatar_getter.getArena()
            if arena is None:
                debug("[WinChance] Arena is None in _get_players_data")
                return players_data
            
            vehicles = arena.vehicles
            debug("[WinChance] Found {} vehicles in arena".format(len(vehicles)))
            
            # Пытаемся получить данные XVM разными способами
            xvm_data_source = self._find_xvm_data_source()
            
            for vehicle_id, vehicle_info in vehicles.items():
                try:
                    # Безопасное получение базовой информации
                    team = vehicle_info.get('team', 0) if isinstance(vehicle_info, dict) else getattr(vehicle_info, 'team', 0)
                    name = vehicle_info.get('name', '') if isinstance(vehicle_info, dict) else getattr(vehicle_info, 'name', '')
                    account_id = vehicle_info.get('accountDBID', 0) if isinstance(vehicle_info, dict) else getattr(vehicle_info, 'accountDBID', 0)
                    
                    player_data = {
                        'team': team,
                        'name': name,
                        'vehicle': '',
                        'stats': {}
                    }
                    
                    # Пытаемся получить статистику из XVM
                    if XVM_AVAILABLE and account_id:
                        xvm_stats = self._get_xvm_stats(account_id, xvm_data_source)
                        if xvm_stats:
                            player_data['stats'] = xvm_stats
                        else:
                            # Используем дефолтные значения
                            player_data['stats'] = {
                                'wgr': 5000,
                                'wins': 0,
                                'battles': 0,
                                'winrate': 50.0
                            }
                    else:
                        # XVM недоступен или нет account_id
                        player_data['stats'] = {
                            'wgr': 5000,
                            'wins': 0,
                            'battles': 0,
                            'winrate': 50.0
                        }
                    
                    players_data[vehicle_id] = player_data
                    
                except Exception as e:
                    debug("[WinChance] Error processing vehicle {}: {}".format(vehicle_id, e))
                    continue
            
            debug("[WinChance] Processed {} players successfully".format(len(players_data)))
            return players_data
            
        except Exception as e:
            err("[WinChance] Error in _get_players_data: {}".format(e))
            import traceback
            err(traceback.format_exc())
            return {}
    
    def _find_xvm_data_source(self):
        """Находит источник данных XVM"""
        try:
            # Метод 1: xvm_main.stats._stat (ПРАВИЛЬНЫЙ СПОСОБ для XVM v13!)
            try:
                import xvm_main.stats as xvm_stats
                if hasattr(xvm_stats, '_stat'):
                    debug("[WinChance] Found xvm_main.stats._stat!")
                    # Проверяем cacheBattle
                    if hasattr(xvm_stats._stat, 'cacheBattle'):
                        debug("[WinChance] Found _stat.cacheBattle with {} entries".format(len(xvm_stats._stat.cacheBattle)))
                        return 'xvm_main.stats._stat.cacheBattle'
                    # Проверяем players
                    if hasattr(xvm_stats._stat, 'players'):
                        debug("[WinChance] Found _stat.players with {} entries".format(len(xvm_stats._stat.players)))
                        return 'xvm_main.stats._stat.players'
            except Exception as e:
                debug("[WinChance] Error accessing xvm_main.stats._stat: {}".format(e))
            
            # Метод 2: battle.players_data
            if hasattr(battle, 'players_data') and battle.players_data:
                debug("[WinChance] Found XVM data in battle.players_data")
                return 'battle.players_data'
            
            debug("[WinChance] No XVM data source found")
            return None
            
        except Exception as e:
            err("[WinChance] Error finding XVM data source: {}".format(e))
            import traceback
            err(traceback.format_exc())
            return None
    
    def _get_xvm_stats(self, account_id, data_source):
        """Получает статистику игрока из XVM"""
        try:
            if not data_source:
                return None
            
            # xvm_main.stats._stat.cacheBattle - ГЛАВНЫЙ ИСТОЧНИК!
            if data_source == 'xvm_main.stats._stat.cacheBattle':
                import xvm_main.stats as xvm_stats
                if hasattr(xvm_stats, '_stat') and hasattr(xvm_stats._stat, 'cacheBattle'):
                    cache = xvm_stats._stat.cacheBattle
                    
                    # Кеш использует ключи вида "accountDBID=vehCD" или просто "accountDBID"
                    # Пробуем оба формата
                    for cache_key in cache.keys():
                        if str(account_id) in cache_key:
                            stat = cache[cache_key]
                            return self._extract_stats_from_xvm_data(stat)
            
            # xvm_main.stats._stat.players
            elif data_source == 'xvm_main.stats._stat.players':
                import xvm_main.stats as xvm_stats
                if hasattr(xvm_stats, '_stat') and hasattr(xvm_stats._stat, 'players'):
                    players = xvm_stats._stat.players
                    
                    # Ищем игрока по accountDBID
                    for vehicle_id, player in players.items():
                        if hasattr(player, 'accountDBID') and player.accountDBID == account_id:
                            log("[WinChance] Found player in _stat.players")
                            # Это объект _Player, нужны реальные статы из cache
                            return None  # Fallback to default
            
            # Старые методы
            elif data_source == 'battle.players_data':
                if hasattr(battle, 'players_data'):
                    player_data = battle.players_data.get(account_id)
                    if player_data:
                        return self._extract_stats_from_xvm_data(player_data)
            
            return None
            
        except Exception as e:
            log("[WinChance] Error getting XVM stats for account {}: {}".format(account_id, e))
            import traceback
            err(traceback.format_exc())
            return None
    
    def _extract_stats_from_xvm_data(self, player_data):
        """Извлекает статистику из данных XVM"""
        try:
            # XVM может хранить данные в разных форматах
            # Пробуем разные варианты
            
            stats = {}
            
            # Вариант 1: Прямые поля
            if isinstance(player_data, dict):
                stats['wgr'] = player_data.get('wgr', player_data.get('WGR', 0))
                stats['xwgr'] = player_data.get('xwgr', player_data.get('XWGR', 0))
                stats['wins'] = player_data.get('w', player_data.get('wins', 0))
                stats['battles'] = player_data.get('b', player_data.get('battles', 0))
                stats['winrate'] = player_data.get('wr', player_data.get('winrate', 0))
            
            # Вариант 2: Вложенная структура
            elif hasattr(player_data, 'stats'):
                xvm_stats = player_data.stats
                stats['wgr'] = getattr(xvm_stats, 'wgr', 0)
                stats['wins'] = getattr(xvm_stats, 'w', 0)
                stats['battles'] = getattr(xvm_stats, 'b', 0)
            
            # Проверяем, что получили хоть что-то полезное
            if stats.get('wgr', 0) > 0 or stats.get('battles', 0) > 0:
                # Если нет WGR, но есть battles/wins, рассчитываем
                if stats.get('wgr', 0) == 0 and stats.get('battles', 0) > 0:
                    winrate = (stats['wins'] / float(stats['battles'])) * 100 if stats['battles'] > 0 else 50.0
                    stats['wgr'] = 5000 + (winrate - 50.0) * 175  # Простая оценка
                
                return stats
            
            return None
            
        except Exception as e:
            debug("[WinChance] Error extracting stats: {}".format(e))
            return None

    
    def _show_display(self):
        """Отображает шанс на победу"""
        try:
            calc = self.calculator
            
            # Формируем простое текстовое сообщение
            message = "Win Chance: {:.1f}% | Ally WGR: {:.0f} | Enemy WGR: {:.0f}".format(
                calc.win_chance, calc.ally_wgr, calc.enemy_wgr)
            
            # Обновляем overlay
            self.overlay.update_text(message)
            
            # Логируем результат
            log("[WinChance] " + message)
                
        except Exception as e:
            err("[WinChance] Error in _show_display: {}".format(e))
    
    def _format_display_text(self):
        """
        Форматирует текст для отображения
        
        Returns:
            str: Форматированный текст
        """
        calc = self.calculator
        
        # Определяем цвет на основе шанса
        if calc.win_chance >= 60:
            color_start = "<font color='#00FF00'>"  # Зеленый
        elif calc.win_chance >= 45:
            color_start = "<font color='#FFFF00'>"  # Желтый
        else:
            color_start = "<font color='#FF0000'>"  # Красный
        
        color_end = "</font>"
        
        text = "<textformat leading='-2'>"
        text += "<font size='16' face='$FieldFont'>"
        text += "<b>Шанс победы:</b> {}{:.1f}%{}<br/>".format(
            color_start, calc.win_chance, color_end)
        text += "<font size='13'>"
        text += "WGR союзники: <font color='#00FF00'>{:.0f}</font><br/>".format(calc.ally_wgr)
        text += "WGR противники: <font color='#FF0000'>{:.0f}</font>".format(calc.enemy_wgr)
        text += "</font>"
        text += "</font>"
        text += "</textformat>"
        
        return text
    
    def _show_message(self, message):
        """Показывает сообщение в игре"""
        try:
            # Метод 1: Используем SystemMessages для показа уведомлений
            try:
                from gui.SystemMessages import pushMessage
                pushMessage(message, type='information')
                return
            except:
                pass
            
            # Метод 2: Messenger в чат
            try:
                from messenger import MessengerEntry
                MessengerEntry.g_instance.gui.addClientMessage(message)
                return
            except:
                pass
            
            # Метод 3: Battle messenger
            try:
                player = BigWorld.player()
                if hasattr(player, 'guiSessionProvider'):
                    ctrl = player.guiSessionProvider.shared.messages
                    if ctrl:
                        ctrl.showMessage('information', message, {'text': message})
                        return
            except:
                pass
            
            # Fallback - просто логируем
            log("[WinChance] {}".format(message))
            
        except Exception as e:
            debug("[WinChance] Error showing message: {}".format(e))
    
    def _hide_display(self):
        """Скрывает отображение"""
        try:
            # Ничего не делаем - сообщения в чате остаются
            pass
        except Exception as e:
            err("[WinChance] Error in _hide_display: {}".format(e))
    
    def _collect_battle_info(self):
        """Собирает информацию о текущем бое"""
        try:
            arena = avatar_getter.getArena()
            if arena is None:
                return
            
            player = BigWorld.player()
            if not hasattr(player, 'vehicleTypeDescriptor'):
                return
            
            # Получаем ID боя
            battle_id = getattr(arena, 'arenaUniqueID', 'Unknown')
            
            # Время начала боя
            start_time = get_current_time()
            
            # Получаем информацию о танке игрока
            vehicle_desc = player.vehicleTypeDescriptor
            vehicle_type = vehicle_desc.type
            
            # Полное имя танка
            vehicle_name = vehicle_type.userString if hasattr(vehicle_type, 'userString') else 'Unknown'
            
            # ID танка (compDescr)
            vehicle_id = getattr(player, 'vehicleID', 0)
            
            # Имя игрока
            player_name = getattr(player, 'name', 'Unknown')
            
            self.current_battle_data = {
                'battle_id': str(battle_id),
                'start_time': start_time,
                'player_name': player_name,
                'player_vehicle_id': vehicle_id,
                'player_vehicle_name': vehicle_name,
                'win_chance': 0,
                'ally_wgr': 0,
                'enemy_wgr': 0
            }
            
            log("[WinChance] Battle info collected: ID={}, Vehicle={}".format(
                battle_id, vehicle_name))
            
        except Exception as e:
            err("[WinChance] Error collecting battle info: {}".format(e))
            import traceback
            err(traceback.format_exc())
    
    def _save_battle_results(self):
        """Сохраняет предсказание шанса на победу в лог файл"""
        try:
            if self.current_battle_data is None:
                debug("[WinChance] No battle data to save")
                return
            
            # Обновляем данные рассчитанными значениями
            self.current_battle_data['win_chance'] = self.calculator.win_chance
            self.current_battle_data['ally_wgr'] = self.calculator.ally_wgr
            self.current_battle_data['enemy_wgr'] = self.calculator.enemy_wgr
            
            # Логируем через BattleLogger (для истории всех боев)
            self.logger.log_battle_result(self.current_battle_data)
            
            # Сохраняем предсказание для последующей отправки в API после окончания боя
            self.result_logger.save_prediction(self.current_battle_data)
            
            log("[WinChance] Battle prediction saved: win_chance={:.1f}%, ally_wgr={:.0f}, enemy_wgr={:.0f}".format(
                self.calculator.win_chance, self.calculator.ally_wgr, self.calculator.enemy_wgr))
            
        except Exception as e:
            err("[WinChance] Error saving battle results: {}".format(e))
            import traceback
            err(traceback.format_exc())
    
    def _collect_battle_statistics(self):
        """Собирает статистику из результатов боя"""
        try:
            player = BigWorld.player()
            if not player:
                log("[WinChance] Cannot collect statistics - player not available")
                return
            
            # Пытаемся получить статистику из разных источников
            stats_collected = False
            
            # Источник 1: player.battleResults (если доступен)
            if hasattr(player, 'battleResults') and player.battleResults:
                try:
                    results = player.battleResults
                    # Обновляем stats_collector
                    if hasattr(results, 'damageDealt'):
                        self.stats_collector.damage_dealt = getattr(results, 'damageDealt', 0)
                    if hasattr(results, 'damageAssisted'):
                        self.stats_collector.damage_assisted = getattr(results, 'damageAssisted', 0)
                    if hasattr(results, 'damageBlocked'):
                        self.stats_collector.damage_blocked = getattr(results, 'damageBlocked', 0)
                    if hasattr(results, 'kills'):
                        self.stats_collector.kills = getattr(results, 'kills', 0)
                    if hasattr(results, 'spotted'):
                        self.stats_collector.spotted = getattr(results, 'spotted', 0)
                    if hasattr(results, 'shots'):
                        self.stats_collector.shots = getattr(results, 'shots', 0)
                    if hasattr(results, 'hits'):
                        self.stats_collector.hits = getattr(results, 'hits', 0)
                    if hasattr(results, 'pierced'):
                        self.stats_collector.penetrations = getattr(results, 'pierced', 0)
                    
                    stats_collected = True
                    log("[WinChance] Battle statistics collected from battleResults")
                except Exception as e:
                    debug("[WinChance] Error collecting from battleResults: {}".format(e))
            
            # Источник 2: Простые атрибуты player (fallback)
            if not stats_collected:
                try:
                    # Пытаемся получить базовую статистику
                    if hasattr(player, 'damageDealt'):
                        self.stats_collector.damage_dealt = getattr(player, 'damageDealt', 0)
                    if hasattr(player, 'kills'):
                        self.stats_collector.kills = getattr(player, 'kills', 0)
                    
                    log("[WinChance] Basic statistics collected from player")
                except Exception as e:
                    debug("[WinChance] Error collecting basic stats: {}".format(e))
            
            log("[WinChance] Statistics: damage={}, kills={}, shots={}".format(
                self.stats_collector.damage_dealt,
                self.stats_collector.kills,
                self.stats_collector.shots
            ))
            
        except Exception as e:
            err("[WinChance] Error collecting battle statistics: {}".format(e))
            import traceback
            err(traceback.format_exc())
    
    def _save_battle_result(self, battle_id, player_team, winner_team):
        """Сохраняет результат боя"""
        try:
            # Собираем статистику из результатов боя
            self._collect_battle_statistics()
            
            # Определяем победу/поражение/ничью
            if winner_team == 0:
                # winner_team = 0 означает ничью
                team_result = 3  # Draw
                win = False
                result_str = 'draw'
            elif winner_team == player_team:
                # Наша команда победила
                team_result = 1  # Win
                win = True
                result_str = 'win'
            else:
                # Вражеская команда победила
                team_result = 2  # Lose
                win = False
                result_str = 'lose'
            
            # Сохраняем результат
            self.result_logger.save_result(
                battle_id=battle_id,
                win=win,
                team_result=team_result,
                personal_result="Win" if win else "Loss"
            )
            
            log("[WinChance] Battle result saved to file")
            
            # Отправляем в API
            log("[WinChance] Preparing API data for battle result: {}".format(result_str))
            
            # Проверяем конфигурацию API
            if not API_CONFIG['enabled']:
                log("[WinChance] API is disabled, skipping API submission")
                return
            
            if not API_CONFIG.get('token'):
                log("[WinChance] API token not configured, skipping API submission")
                return
            
            # Подготавливаем данные с учетом рассчитанных шансов
            api_data = self.stats_collector.prepare_api_data(
                battle_result=result_str,
                win_chance=self.calculator.win_chance,
                ally_wgr=self.calculator.ally_wgr,
                enemy_wgr=self.calculator.enemy_wgr
            )
            
            if api_data:
                log("[WinChance] API data prepared successfully, sending to API...")
                log("[WinChance] API data: ArenaId={}, Result={}, Tank={}".format(
                    api_data.get('ArenaUniqueId'),
                    api_data.get('Result'),
                    api_data.get('Tank', {}).get('Name', 'Unknown')
                ))
                success = send_battle_to_api(api_data)
                if success:
                    log("[WinChance] Battle successfully sent to API")
                else:
                    err("[WinChance] Failed to send battle to API")
            else:
                err("[WinChance] Failed to prepare API data - prepare_api_data returned None")
        
        except Exception as e:
            err("[WinChance] Error saving battle result: {}".format(e))
            import traceback
            err(traceback.format_exc())
    
    def _subscribe_to_battle_events(self):
        """Подписывается на события боя для получения результатов"""
        try:
            # Подписка происходит через мониторинг арены в _check_arena_period
            log("[WinChance] Battle event subscription initialized")
        except Exception as e:
            err("[WinChance] Error subscribing to battle events: {}".format(e))
    
    def _save_arena_data_for_results(self):
        """Сохраняет данные арены для последующего получения результатов"""
        try:
            arena = avatar_getter.getArena()
            if arena is None:
                log("[WinChance] Cannot save arena data - arena is None")
                return
            
            player = BigWorld.player()
            if not hasattr(player, 'team'):
                log("[WinChance] Cannot save arena data - no player team")
                return
            
            # Сохраняем данные
            self.saved_battle_id = getattr(arena, 'arenaUniqueID', None)
            self.saved_player_team = player.team
            self.monitoring_active = True
            
            log("[WinChance] Arena data saved: Battle ID={}, Team={}".format(
                self.saved_battle_id, self.saved_player_team))
            
            # Начинаем мониторить период арены для определения окончания боя
            self._start_arena_monitoring()
            
        except Exception as e:
            err("[WinChance] Error saving arena data: {}".format(e))
            import traceback
            err(traceback.format_exc())
    
    def _start_arena_monitoring(self):
        """Начинает мониторинг арены для определения окончания боя"""
        try:
            self.saved_arena_period_callback = BigWorld.callback(1.0, self._check_arena_period)
            log("[WinChance] Arena monitoring started")
        except Exception as e:
            err("[WinChance] Error starting arena monitoring: {}".format(e))
    
    def _check_arena_period(self):
        """Проверяет период боя и пытается получить результаты"""
        try:
            # Проверяем что мониторинг еще активен
            if not self.monitoring_active:
                log("[WinChance] Monitoring was stopped externally")
                return
            
            # Проверяем наличие арены независимо от статуса игрока
            arena = avatar_getter.getArena()
            if arena is None:
                # Арена исчезла - останавливаем мониторинг
                log("[WinChance] Arena disappeared, stopping monitoring")
                self.monitoring_active = False
                self.saved_arena_period_callback = None
                return
            
            # Проверяем что это тот же бой, который мы мониторим
            current_arena_id = getattr(arena, 'arenaUniqueID', None)
            if current_arena_id != self.saved_battle_id:
                log("[WinChance] Arena ID changed ({} != {}), stopping old monitoring".format(
                    current_arena_id, self.saved_battle_id))
                self.monitoring_active = False
                self.saved_arena_period_callback = None
                return
            
            # Проверяем период боя
            period = getattr(arena, 'period', None)
            
            # Период 3 = PERIOD_AFTERBATTLE (бой закончен)
            if period == 3:
                log("[WinChance] Battle finished detected (period=3)")
                self._try_get_battle_results_from_arena(arena)
                # Останавливаем мониторинг после получения результатов
                self.monitoring_active = False
                self.saved_arena_period_callback = None
                return
            
            # Продолжаем мониторинг пока арена существует
            if self.monitoring_active:
                self.saved_arena_period_callback = BigWorld.callback(1.0, self._check_arena_period)
            
        except Exception as e:
            err("[WinChance] Error in _check_arena_period: {}".format(e))
            import traceback
            err(traceback.format_exc())
            # При ошибке останавливаем мониторинг
            self.monitoring_active = False
            self.saved_arena_period_callback = None
    
    def _try_get_battle_results_from_arena(self, arena):
        """Получает результаты боя из арены"""
        try:
            if arena is None:
                log("[WinChance] Cannot get results - arena is None")
                return
            
            # Получаем команду-победителя
            winner_team = getattr(arena, 'winnerTeam', 0)
            
            # Альтернативный способ через periodAdditionalInfo
            if winner_team == 0:
                period_info = getattr(arena, 'periodAdditionalInfo', None)
                if period_info:
                    # periodAdditionalInfo содержит информацию о победителе
                    if isinstance(period_info, (list, tuple)) and len(period_info) > 0:
                        winner_team = period_info[0]
            
            # Еще один способ - через vehicles
            if winner_team == 0:
                vehicles = getattr(arena, 'vehicles', {})
                team1_alive = 0
                team2_alive = 0
                
                for vehicle_id, vehicle_info in vehicles.items():
                    if isinstance(vehicle_info, dict):
                        team = vehicle_info.get('team', 0)
                        is_alive = vehicle_info.get('isAlive', False)
                    else:
                        team = getattr(vehicle_info, 'team', 0)
                        is_alive = getattr(vehicle_info, 'isAlive', False)
                    
                    if is_alive:
                        if team == 1:
                            team1_alive += 1
                        elif team == 2:
                            team2_alive += 1
                
                if team1_alive > 0 and team2_alive == 0:
                    winner_team = 1
                elif team2_alive > 0 and team1_alive == 0:
                    winner_team = 2
            
            # Используем сохраненные данные
            battle_id = self.saved_battle_id
            player_team = self.saved_player_team
            
            if battle_id is None or player_team is None:
                log("[WinChance] Missing saved data for result logging")
                return
            
            log("[WinChance] Battle result detected: Winner={}, Player team={}".format(
                winner_team, player_team))
            
            # Сохраняем результат
            self._save_battle_result(battle_id, player_team, winner_team)
            
        except Exception as e:
            err("[WinChance] Error getting battle results from arena: {}".format(e))
            import traceback
            err(traceback.format_exc())
    


# Глобальный экземпляр
_display = None
_monitor_callback_id = None
_registration_attempted = False  # Флаг для отслеживания попыток регистрации


def init():
    """Инициализация мода"""
    global _display, _monitor_callback_id
    
    try:
        log("[WinChance] Initializing mod...")
        
        # Загружаем конфиг API
        load_api_config()
        
        # Проверяем подключение к API
        if API_CONFIG['enabled']:
            log("[WinChance] Testing API connection...")
            if test_api_connection():
                # API доступен - проверяем регистрацию
                check_and_register_if_needed()
            else:
                log("[WinChance] API is not available, will try later")
        
        # Создаем дисплей
        _display = WinChanceDisplay()
        
        # Запускаем мониторинг состояния боя
        _start_battle_monitor()
        
        log("[WinChance] Mod initialized successfully")
        
    except Exception as e:
        err("[WinChance] Error in init: {}".format(e))
        import traceback
        err(traceback.format_exc())


def fini():
    """Финализация мода"""
    global _display, _monitor_callback_id
    
    try:
        log("[WinChance] Shutting down mod...")
        
        # Останавливаем мониторинг
        if _monitor_callback_id is not None:
            BigWorld.cancelCallback(_monitor_callback_id)
            _monitor_callback_id = None
        
        if _display:
            _display.on_battle_end()
            _display = None
        
        log("[WinChance] Mod shut down successfully")
        
    except Exception as e:
        err("[WinChance] Error in fini: {}".format(e))


def _start_battle_monitor():
    """Запускает мониторинг состояния боя"""
    global _monitor_callback_id
    _monitor_callback_id = BigWorld.callback(0.5, _check_battle_state)
    log("[WinChance] Battle monitor started")


def _check_battle_state():
    """Проверяет текущее состояние боя"""
    global _display, _monitor_callback_id, _registration_attempted
    
    try:
        if _display is None:
            return
        
        # Проверяем регистрацию в API (если еще не зарегистрированы)
        if API_CONFIG['enabled'] and not API_CONFIG.get('token') and not _registration_attempted:
            # Проверяем доступность информации о игроке
            player_info = get_player_info()
            if player_info:
                log("[WinChance] Player info now available, attempting registration...")
                _registration_attempted = True  # Предотвращаем повторные попытки в этой сессии
                if check_and_register_if_needed():
                    log("[WinChance] Registration in hangar successful!")
        
        # Проверяем, есть ли активная арена
        player = BigWorld.player()
        arena = avatar_getter.getArena()
        
        is_in_battle = arena is not None and hasattr(player, 'team')
        
        # Если состояние изменилось
        if is_in_battle and not _display.is_in_battle:
            # Бой начался
            debug("[WinChance] Battle detected, starting...")
            _display.on_battle_start()
        elif not is_in_battle and _display.is_in_battle:
            # Бой закончился
            debug("[WinChance] Battle ended, stopping...")
            _display.on_battle_end()
        
    except Exception as e:
        err("[WinChance] Error in battle state check: {}".format(e))
    finally:
        # Планируем следующую проверку
        _monitor_callback_id = BigWorld.callback(0.5, _check_battle_state)


# ---------------------------------------------------------------------
# Hook Account.onBattleResultsReceived для получения результатов в ангаре
# ---------------------------------------------------------------------
# ---------------------------------------------------------------------
# Hook Account.onBattleResultsReceived для получения результатов в ангаре
# ---------------------------------------------------------------------
try:
    if hasattr(Account.Account, 'onBattleResultsReceived'):
        _original_onBattleResultsReceived = Account.Account.onBattleResultsReceived

        def hooked_onBattleResultsReceived(self, accountDBID, stuck, result):
            """Хук для перехвата результатов боя"""
            try:
                if _display:
                    # Мы вызываем обработчик в Display
                    _display.on_hangar_result(result)
            except Exception as e:
                err("[WinChance] Error in hooked_onBattleResultsReceived: {}".format(e))
            
            # Вызываем оригинальный метод
            return _original_onBattleResultsReceived(self, accountDBID, stuck, result)

        Account.Account.onBattleResultsReceived = hooked_onBattleResultsReceived
        log("[WinChance] Hooked Account.onBattleResultsReceived successfully")
    else:
        log("[WinChance] Account.onBattleResultsReceived not found on class, skipping hook (Early exit results disabled)")

except Exception as e:
    err("[WinChance] Failed to hook Account.onBattleResultsReceived: {}".format(e))


# Добавляем метод обработки в WinChanceDisplay
def on_hangar_result(self, result):
    """Обрабатывает результаты, полученные в ангаре"""
    try:
        if not result:
            return
            
        # Распаковываем результат если нужно
        # Обычно это уже распакованный объект или pickle строка
        # Пробуем распарсить
        battle_results = None
        
        if isinstance(result, str):
            try:
                battle_results = pickle.loads(result)
            except Exception:
                pass
        
        if not battle_results and isinstance(result, dict):
             battle_results = result
             
        if not battle_results:
            # log("[WinChance] Unknown battle result format")
            return

        # Извлекаем arenaUniqueId
        arena_id = battle_results.get('arenaUniqueId')
        if not arena_id:
            return
            
        # Проверяем, ждем ли мы этот бой
        pending_battle = self.result_logger.get_pending_battle(arena_id)
        if not pending_battle:
            return
            
        log("[WinChance] Received battle results for pending arena: {}".format(arena_id))
        
        # Находим статистику нашего игрока
        # battle_results structure: {'personal': {accountDBID: {...stats...}}, 'common': {...}, ...}
        
        personal = battle_results.get('personal', {})
        # Ищем по всем ключам, т.к. accountDBID может быть строкой или int
        my_stats = None
        for acc_id, stats in personal.items():
            # Если это список (обычно один элемент 0)
            if isinstance(stats, dict):
                 my_stats = stats
                 break
        
        if my_stats:
             # Обновляем stats_collector временными данными
             # Структура my_stats обычно содержит damageDealt и т.д.
             
             # Безопасное извлечение
            damage_dealt = my_stats.get('damageDealt', 0)
            kills = my_stats.get('kills', 0)
            shots = my_stats.get('shots', 0)
            # ... другие поля ...
            
            # Создаем временный коллектор или обновляем существующий
            # Но лучше сформировать api_data напрямую, так как мы не в бою
            
            result_str = pending_battle.get('result', 'draw') # Default, update from winner
            
            # Определяем победителя из common
            common = battle_results.get('common', {})
            winner_team = common.get('winnerTeam', 0) # 0 - draw, 1, 2
            
            # team is pending_battle['team']
            player_team = pending_battle.get('team', 1)
            
            if winner_team == 0:
                result_str = 'draw'
                win = False
                team_result = 0
            elif winner_team == player_team:
                result_str = 'win'
                win = True
                team_result = 1
            else:
                result_str = 'lose'
                win = False
                team_result = 2

            # Формируем DTO
            api_data = {
                'ArenaUniqueId': arena_id,
                'BattleTime': pending_battle.get('battleTime', get_current_time()),
                'MapName': pending_battle.get('mapName', 'Unknown'),
                'BattleType': pending_battle.get('battleType', 'random'),
                'Team': player_team,
                'Result': result_str,
                
                'WinChance': pending_battle.get('win_chance', 0),
                'AllyWgr': pending_battle.get('ally_wgr', 0),
                'EnemyWgr': pending_battle.get('enemy_wgr', 0),
                
                'DamageDealt': damage_dealt,
                'DamageAssisted': my_stats.get('damageAssisted', 0) + my_stats.get('damageAssistedRadio', 0) + my_stats.get('damageAssistedTrack', 0),
                'DamageBlocked': my_stats.get('damageBlockedByArmor', 0),
                'Kills': kills,
                'Spotted': my_stats.get('spotted', 0),
                'Experience': my_stats.get('xp', 0),
                'Credits': my_stats.get('credits', 0),
                'Shots': shots,
                'Hits': my_stats.get('directHits', 0),
                'Penetrations': my_stats.get('piercings', 0),
                
                'Tank': pending_battle.get('tank', {})
            }
            
            log("[WinChance] API data prepared from Hangar results")
            
            # Отправляем
            if API_CONFIG['enabled'] and API_CONFIG.get('token'):
                success = send_battle_to_api(api_data)
                if success:
                    log("[WinChance] Pending battle successfully sent to API")
            
            # Сохраняем в лог
            self.result_logger.save_result(arena_id, win, team_result, "Win" if win else "Loss")

    except Exception as e:
        err("[WinChance] Error handling hangar result: {}".format(e))
        import traceback
        err(traceback.format_exc())

WinChanceDisplay.on_hangar_result = on_hangar_result

