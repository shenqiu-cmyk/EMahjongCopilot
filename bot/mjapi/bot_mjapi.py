# FILE: bot_mjapi.py

""" Bot for mjapi"""

import time
from common.settings import Settings
from common.log_helper import LOGGER
from common.utils import random_str
from common.mj_helper import MjaiType
from bot.mjapi.mjapi import MjapiClient
from bot.bot import Bot, GameMode


class BotMjapi(Bot):
    """
    A bot that uses an online MJAPI service for decision-making.
    It supports both 3-player and 4-player modes by selecting the appropriate model.
    """
    # --- Class constants for configuration ---
    batch_size = 24  # The number of messages to send in a single batch request.
    retries = 3  # The number of times to retry a failed API request.
    retry_interval = 1  # The number of seconds to wait between retries.
    bound = 256  # The buffer size for message sequencing with the API.

    def __init__(self, setting: Settings) -> None:
        """
        Initializes the MJAPI bot, logs into the service, and validates available models.
        """
        super().__init__("MJAPI Bot")
        self.st = setting
        self.api_usage = None
        self.mjapi = MjapiClient(self.st.mjapi_url)
        
        # Choose login method based on available credentials
        if hasattr(self.st, 'mjapi_session_id') and self.st.mjapi_session_id:
            self._login_with_session()
        else:
            self._login_or_reg()

        self.id = -1
        self.ignore_next_turn_self_reach: bool = False
        self._supported_modes: list[GameMode] = []
        self.current_model_name: str = ""
        self.current_mode: GameMode | None = None  # Store the current game mode.

        self._configure_models()

    @property
    def supported_modes(self) -> list[GameMode]:
        """
        Returns a list of game modes supported by the configured MJAPI models.

        Returns:
            list[GameMode]: A list containing GameMode.MJ4P and/or GameMode.MJ3P.
        """
        return self._supported_modes

    @property
    def info_str(self):
        """
        Provides a descriptive string for the bot, including the currently active model.

        Returns:
            str: A formatted string with bot name, active model, and API usage.
        """
        model_display = self.current_model_name if self.current_model_name else "N/A"
        return f"{self.name} [{model_display}] (Usage: {self.api_usage})"

    def _login_or_reg(self):
        """
        Handles the login or registration process with the MJAPI service using username/secret.
        """
        if not self.st.mjapi_user:
            self.st.mjapi_user = random_str(6)
            LOGGER.info("Created random mjapi username:%s", self.st.mjapi_user)
        if self.st.mjapi_secret:
            LOGGER.debug("Logging in with user: %s", self.st.mjapi_user)
            self.mjapi.login(self.st.mjapi_user, self.st.mjapi_secret)
        else:
            LOGGER.debug("Registering with user: %s", self.st.mjapi_user)
            res_reg = self.mjapi.register(self.st.mjapi_user)
            self.st.mjapi_secret = res_reg['secret']
            self.st.save_json()
            LOGGER.info("Registered new user [%s] with MJAPI.", self.st.mjapi_user)
            self.mjapi.login(self.st.mjapi_user, self.st.mjapi_secret)

    def _login_with_session(self):
        """
        Use existing session ID for login, skipping registration or login process.
        """
        if not self.st.mjapi_session_id:
            raise RuntimeError("Session ID is required for login.")

        LOGGER.debug("Logging in with session ID: %s", self.st.mjapi_session_id)
        self.mjapi.login_with_session(self.st.mjapi_session_id)

    def _configure_models(self):
        """
        Fetches available models from the API, filters them into 3p and 4p,
        and validates the user's selections.
        """
        # Fetch all available models from the MJAPI service.
        all_models = self.mjapi.list_models()
        if not all_models:
            raise RuntimeError("No models available in MJAPI")

        # Store all models in settings for user selection in a UI.
        self.st.mjapi_models = all_models

        # Filter models into 3-player and 4-player categories based on their names.
        models_3p = [m for m in all_models if "3p" in m]
        models_4p = [m for m in all_models if "4p" in m]

        LOGGER.info(f"Available MJAPI models: 4p={models_4p}, 3p={models_3p}")

        # Validate 4-player model selection.
        if models_4p:
            if self.st.mjapi_model_select_4p not in models_4p:
                self.st.mjapi_model_select_4p = models_4p[0]  # Default to the first available 4p model.
                LOGGER.warning(f"Selected 4p model not found. Defaulting to {self.st.mjapi_model_select_4p}")
            self._supported_modes.append(GameMode.MJ4P)  # Add 4P to supported modes.

        # Validate 3-player model selection.
        if models_3p:
            if self.st.mjapi_model_select_3p not in models_3p:
                self.st.mjapi_model_select_3p = models_3p[0]  # Default to the first available 3p model.
                LOGGER.warning(f"Selected 3p model not found. Defaulting to {self.st.mjapi_model_select_3p}")
            self._supported_modes.append(GameMode.MJ3P)  # Add 3P to supported modes.

        # Update API usage and save any changes to settings.
        self.api_usage = self.mjapi.get_usage()
        self.st.save_json()
        LOGGER.info(
            "MJAPI login successful. Supported modes: %s",
            self._supported_modes
        )

    def __del__(self):
        """
        Destructor to ensure clean shutdown, stopping the bot and logging out.
        """
        LOGGER.debug("Deleting bot %s", self.name)
        if self.initialized:  # If a game was started...
            self.mjapi.stop_bot()  # ...ensure the bot is stopped on the server.
        if self.mjapi.token:  # If we were logged in...
            self.st.mjapi_usage = self.mjapi.get_usage()  # ...update final usage count.
            self.st.save_json()  # ...save settings.
            self.mjapi.logout()  # ...and log out.

    def _init_bot_impl(self, mode: GameMode = GameMode.MJ4P):
        """
        Initializes a new game session with the API, selecting the model based on game mode.
        """
        # Store the current mode for later use.
        self.current_mode = mode

        if mode == GameMode.MJ4P:
            model_to_use = self.st.mjapi_model_select_4p
        elif mode == GameMode.MJ3P:
            model_to_use = self.st.mjapi_model_select_3p
        else:
            raise ValueError(f"MJAPI bot does not support game mode: {mode}")

        self.current_model_name = model_to_use
        LOGGER.info(f"Starting MJAPI bot for {mode.name} using model: {self.current_model_name}")
        self.mjapi.start_bot(self.seat, BotMjapi.bound, self.current_model_name)
        self.id = -1

    def _preprocess_for_3p(self, msg: dict) -> dict:
        """
        Corrects message formats for 3-player games before sending to the API.
        Specifically, it trims 'scores' and 'tehais' arrays in 'start_kyoku' events.
        """
        # We only need to act if we are in a 3-player game.
        if self.current_mode != GameMode.MJ3P:
            return msg

        # Check if this is the message that needs correcting.
        if msg.get('type') == MjaiType.START_KYOKU:
            LOGGER.debug(f"Preprocessing 3p start_kyoku message. Original scores length: {len(msg.get('scores', []))}")
            
            # Create a shallow copy to avoid modifying the original data structure.
            msg_copy = msg.copy()
            
            # If 'scores' exists and has 4 elements, trim it to 3.
            if 'scores' in msg_copy and len(msg_copy['scores']) == 4:
                msg_copy['scores'] = msg_copy['scores'][:3]
                LOGGER.info("Trimmed 'scores' array to 3 elements for 3p mode.")
            
            # If 'tehais' exists and has 4 elements, trim it to 3.
            if 'tehais' in msg_copy and len(msg_copy['tehais']) == 4:
                msg_copy['tehais'] = msg_copy['tehais'][:3]
                LOGGER.info("Trimmed 'tehais' array to 3 elements for 3p mode.")
            
            return msg_copy

        # For all other message types, return the original message.
        return msg

    def _process_reaction(self, reaction, recurse):
        """
        Processes the reaction from the API, handling special cases like self-reach.
        This version includes robust checks to handle non-standard API responses.

        Args:
            reaction (dict | None): The JSON response from the API.
            recurse (bool): Flag to prevent infinite recursion on reach calls.

        Returns:
            dict | None: A valid Mjai action dictionary, or None.
        """
        # Robust check for a valid Mjai action
        if not isinstance(reaction, dict) or 'type' not in reaction:
            return None

        # Process self reach: if the bot declares reach, we immediately ask it what to discard.
        if recurse and reaction['type'] == MjaiType.REACH and reaction['actor'] == self.seat:
            LOGGER.debug("Send reach msg to get reach_dahai.")
            reach_msg = {'type': MjaiType.REACH, 'actor': self.seat}
            # Make the recursive call to get the discard action following the reach.
            reach_dahai = self.react(reach_msg, recurse=False)
            # Embed the discard action into the original reach action.
            reaction['reach_dahai'] = self._process_reaction(reach_dahai, False)
            # Set a flag to ignore the next turn's reach event, as we've already handled it.
            self.ignore_next_turn_self_reach = True

        return reaction

    def react(self, input_msg: dict, recurse=True) -> dict | None:
        msg_type = input_msg['type']
        if self.ignore_next_turn_self_reach:
            if msg_type == MjaiType.REACH and input_msg['actor'] == self.seat:
                LOGGER.debug("Ignoring repetitive self reach msg")
                return None
            self.ignore_next_turn_self_reach = False

        old_id = self.id
        err = None
        self.id = (self.id + 1) % BotMjapi.bound
        reaction = None
        for _ in range(BotMjapi.retries):
            try:
                reaction = self.mjapi.act(self.id, input_msg)
                err = None
                break
            except Exception as e:
                err = e
                time.sleep(BotMjapi.retry_interval)
        if err:
            self.id = old_id
            raise err
        return self._process_reaction(reaction, recurse)

    def react_batch(self, input_list: list[dict]) -> dict | None:
        if self.ignore_next_turn_self_reach and len(input_list) > 0:
            if input_list[0]['type'] == MjaiType.REACH and input_list[0]['actor'] == self.seat:
                LOGGER.debug("Ignoring repetitive self reach msg")
                input_list = input_list[1:]
            self.ignore_next_turn_self_reach = False
        if len(input_list) == 0:
            return None
        num_batches = (len(input_list) - 1) // BotMjapi.batch_size + 1
        reaction = None
        for (i, start) in enumerate(range(0, len(input_list), BotMjapi.batch_size)):
            reaction = self._react_batch_impl(
                input_list[start:start + BotMjapi.batch_size],
                can_act=i + 1 == num_batches)
        return reaction

    def _react_batch_impl(self, input_list, can_act):
        """
        Helper function to process a single batch of actions and send it to the API.
        Includes direct pre-processing for 3p games.
        """
        if len(input_list) == 0:
            return None
            
        batch_data = []
        old_id = self.id
        err = None

        # Iterate over the input messages to prepare them for the batch request.
        for (i, original_msg) in enumerate(input_list):
            self.id = (self.id + 1) % BotMjapi.bound
            
            # Make a copy so we don't alter the original log data.
            msg = original_msg.copy()
            
            # Perform pre-processing specific to 3-player mode
            if self.current_mode == GameMode.MJ3P:
                msg_type = msg.get('type')
                # Rule 1: Trim arrays in start_kyoku message.
                if msg_type == MjaiType.START_KYOKU:
                    if 'scores' in msg and len(msg['scores']) == 4:
                        msg['scores'] = msg['scores'][:3]
                        LOGGER.info("Trimmed 'scores' array to 3 elements for 3p mode.")
                    if 'tehais' in msg and len(msg['tehais']) == 4:
                        msg['tehais'] = msg['tehais'][:3]
                        LOGGER.info("Trimmed 'tehais' array to 3 elements for 3p mode.")
                
                # Rule 2: Translate 'nukidora' to 'kita' for the API
                elif msg_type == MjaiType.NUKIDORA:
                    msg['type'] = MjaiType.KITA
                    LOGGER.info("Translated 'nukidora' to 'kita' for 3p API compatibility.")

            # If this is not the last batch, the bot cannot act on this message.
            if i + 1 == len(input_list) and not can_act:
                msg['can_act'] = False
            
            # Format the message for the API.
            action = {'seq': self.id, 'data': msg}
            batch_data.append(action)

        reaction = None
        for _ in range(BotMjapi.retries):
            try:
                # Log the data we are about to send for final verification
                if self.current_mode == GameMode.MJ3P:
                    LOGGER.debug(f"Sending to 3p API: {batch_data}")
                reaction = self.mjapi.batch(batch_data)
                err = None
                break
            except Exception as e:
                err = e
                time.sleep(BotMjapi.retry_interval)

        if err:
            self.id = old_id
            raise err
            
        return self._process_reaction(reaction, True)