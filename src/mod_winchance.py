# -*- coding: utf-8 -*-
"""
Win Chance Mod - Рассчитывает и отображает шанс на победу
"""

import BigWorld
from Avatar import PlayerAvatar
from gui.battle_control import avatar_getter
import os
import math

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


class WinChanceDisplay(object):
    """Класс для отображения шанса на победу"""
    
    def __init__(self):
        self.calculator = WinChanceCalculator()
        self.is_in_battle = False
        self.overlay = DraggableWinChanceWindow()
        self.data_ready = False
        
    def on_battle_start(self):
        """Вызывается при старте боя"""
        try:
            self.is_in_battle = True
            self.data_ready = False
            log("[WinChance] Battle started, waiting for XVM data...")
            
            # Создаем overlay (но не показываем пока нет данных)
            self.overlay.create()
            
            # Даем XVM время загрузить данные, затем рассчитываем один раз
            BigWorld.callback(3.0, self._calculate_once)
            
        except Exception as e:
            err("[WinChance] Error in on_battle_start: {}".format(e))
    
    def on_battle_end(self):
        """Вызывается при окончании боя"""
        try:
            self.is_in_battle = False
            self.data_ready = False
            log("[WinChance] Battle ended")
            
            # Уничтожаем overlay
            self.overlay.destroy()
            
        except Exception as e:
            err("[WinChance] Error in on_battle_end: {}".format(e))
    
    def _calculate_once(self):
        """Рассчитывает win chance один раз когда данные готовы"""
        try:
            if not self.is_in_battle:
                return
            
            log("[WinChance] Calculating win chance...")
            
            # Получаем данные игроков
            arena = avatar_getter.getArena()
            if arena is None:
                log("[WinChance] Arena is None, retrying in 2 sec...")
                BigWorld.callback(2.0, self._calculate_once)
                return
            
            # Получаем команду игрока
            player = BigWorld.player()
            if not hasattr(player, 'team'):
                log("[WinChance] Player has no team, retrying in 2 sec...")
                BigWorld.callback(2.0, self._calculate_once)
                return
            
            player_team = player.team
            log("[WinChance] Player team: {}".format(player_team))
            
            # Получаем данные из XVM
            players_data = self._get_players_data()
            if not players_data:
                log("[WinChance] No players data, retrying in 2 sec...")
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
            
            # Если меньше 20 игроков с реальными данными - ждем еще
            if real_data_count < 20:
                log("[WinChance] Waiting for more XVM data, retrying in 2 sec...")
                BigWorld.callback(2.0, self._calculate_once)
                return
            
            # Данные готовы! Рассчитываем
            log("[WinChance] XVM data ready, calculating...")
            self.calculator.update(players_data, player_team)
            
            # Отображаем результаты
            self._show_display()
            self.data_ready = True
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
                log("[WinChance] Arena is None in _get_players_data")
                return players_data
            
            vehicles = arena.vehicles
            log("[WinChance] Found {} vehicles in arena".format(len(vehicles)))
            
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
                            log("[WinChance] Got XVM stats for {}: WGR={}".format(name, xvm_stats.get('wgr', 0)))
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
                    log("[WinChance] Error processing vehicle {}: {}".format(vehicle_id, e))
                    continue
            
            log("[WinChance] Processed {} players successfully".format(len(players_data)))
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
                    log("[WinChance] Found xvm_main.stats._stat!")
                    # Проверяем cacheBattle
                    if hasattr(xvm_stats._stat, 'cacheBattle'):
                        log("[WinChance] Found _stat.cacheBattle with {} entries".format(len(xvm_stats._stat.cacheBattle)))
                        return 'xvm_main.stats._stat.cacheBattle'
                    # Проверяем players
                    if hasattr(xvm_stats._stat, 'players'):
                        log("[WinChance] Found _stat.players with {} entries".format(len(xvm_stats._stat.players)))
                        return 'xvm_main.stats._stat.players'
            except Exception as e:
                log("[WinChance] Error accessing xvm_main.stats._stat: {}".format(e))
            
            # Метод 2: battle.players_data
            if hasattr(battle, 'players_data') and battle.players_data:
                log("[WinChance] Found XVM data in battle.players_data")
                return 'battle.players_data'
            
            log("[WinChance] No XVM data source found")
            return None
            
        except Exception as e:
            log("[WinChance] Error finding XVM data source: {}".format(e))
            import traceback
            err(traceback.format_exc())
            return None
    
    def _get_xvm_stats(self, account_id, data_source):
        """Получает статистику игрока из XVM"""
        try:
            if not data_source:
                return None
            
            log("[WinChance] Trying to get stats for account {} from {}".format(account_id, data_source))
            
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
                            log("[WinChance] Found stats in cacheBattle for key: {}".format(cache_key))
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


# Глобальный экземпляр
_display = None
_monitor_callback_id = None


def init():
    """Инициализация мода"""
    global _display, _monitor_callback_id
    
    try:
        log("[WinChance] Initializing mod...")
        
        # Создаем дисплей
        _display = WinChanceDisplay()
        
        # Запускаем мониторинг состояния боя
        _start_battle_monitor()
        
        log("[WinChance] Mod initialized successfully")
        
    except Exception as e:
        err("[WinChance] Error in init: {}".format(e))


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
    global _display, _monitor_callback_id
    
    try:
        if _display is None:
            return
        
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

