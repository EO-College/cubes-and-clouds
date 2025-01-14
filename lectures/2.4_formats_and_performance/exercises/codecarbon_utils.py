"""
This module contains code to take codecarbon csv data and calculate the energy consumption
and display the equivalent emissions in terms of distance covered by the Perseverance Rover,
runtime of an LED bulb, and runtime of a smartwatch.

The code also generates an HTML output with the calculated values. This is then fed into the 
html template which we load and display in the jupyter notebook.
"""

import os
import uuid
import logging
import pandas as pd
from IPython.display import display, HTML
from dataclasses import dataclass
from codecarbon import OfflineEmissionsTracker

carbon_logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class CustomEmissionsTracker(OfflineEmissionsTracker):
    """
    Extension of the OfflineEmissionsTracker class to support adding custom experiment IDs to the emissions CSV.
    This does not change the core functionality, it just makes our visualization more robust and less buggy.
    The start and stop experiment methods also ensure the tracking process is stopped due to existing bugs which
    are apparently fixed but I have experienced it many times.

    https://github.com/mlco2/codecarbon/issues/702
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_experiment_id = None
        self.emissions_file = os.path.join(
            kwargs.get("output_dir", "./"), "emissions.csv"
        )

    def start_experiment(self, experiment_id: int = None) -> None:
        """
        Start tracking an experiment with a custom or auto-generated experiment ID.

        Args:
            experiment_id (int): Custom experiment ID. If not provided, a random ID will be generated.

        returns: None
        """
        self.current_experiment_id = experiment_id or uuid.uuid4().hex
        print(f"Starting experiment: {self.current_experiment_id}")
        self._start_time = None
        super().start()

    def stop_experiment(self) -> None:
        """
        Stop tracking the current experiment, appending the experiment ID to the CSV.

        returns: None
        """
        super().stop()
        super().flush()
        if self.current_experiment_id:
            self._append_experiment_id_to_csv()
        print(f"Stopped experiment: {self.current_experiment_id}")

    def _append_experiment_id_to_csv(self) -> None:
        """
        Add the custom experiment ID to the latest entry in the emissions CSV for filtering and identification.

        returns: None
        """
        if os.path.exists(self.emissions_file):
            emissions_data = pd.read_csv(self.emissions_file)
            if emissions_data.empty:
                carbon_logger.error("Emissions CSV is empty.")
                return
            emissions_data.loc[emissions_data.index[-1], "experiment_id"] = (
                self.current_experiment_id
            )
            emissions_data.to_csv(self.emissions_file, index=False)
        else:
            print("Emissions CSV not found. Ensure tracking is properly configured.")


@dataclass(
    slots=True
)  # prevents the automatic creation of __dict__ and __weakref__ for each instance, saving memory.
class EnergyConsumption:
    energy_consumed_kwh: float
    energy_consumed_wh: float = 0.0
    rover_distance_covered: float = 0.0
    led_bulb_runtime: str = ""
    smartwatch_runtime_idle: str = ""
    smartwatch_runtime_normal: str = ""

    def __post_init__(self):
        self.energy_consumed_wh = self.energy_consumed_kwh * 1000

    @staticmethod
    def _convert_seconds_to_readable(seconds: int) -> str:
        """
        Convert seconds to human-readable format

        args:
            seconds (int): Number of seconds to convert

        returns: str
        """
        if seconds >= 3600:
            return f"{seconds / 3600:.2f} hours"
        elif seconds >= 60:
            return f"{seconds / 60:.2f} minutes"
        else:
            return f"{seconds:.2f} seconds"

    def calculate_rover_distance(self) -> None:
        """
        Calculate the distance covered by the Perseverance Rover

        returns: None
        """
        # Perseverance Rover distance
        # https://science.nasa.gov/mission/mars-2020-perseverance/rover-components/
        energy_per_meter = 1.16  # watt-hours per meter
        self.rover_distance_covered = self.energy_consumed_wh / energy_per_meter
        carbon_logger.debug(f"Rover distance covered (meters): {self.rover_distance_covered}")

    def calculate_led_bulb_runtime(self) -> None:
        """
        Calculate the runtime of an LED bulb

        returns: None
        """
        # LED Bulb
        # https://www.researchgate.net/profile/Emina-Pasic/publication/385893166_EFFICIENCY_OF_LED_BULBS_COMPARED_TO_CONVENTIONAL_BULBS_-_ENERGY_CONSUMPTION_STUDY/links/673a206837496239b2c358d3/EFFICIENCY-OF-LED-BULBS-COMPARED-TO-CONVENTIONAL-BULBS-ENERGY-CONSUMPTION-STUDY.pdf
        led_power = 10  # watts
        led_bulb_seconds = (self.energy_consumed_wh * 3600) / led_power
        self.led_bulb_runtime = self._convert_seconds_to_readable(led_bulb_seconds)
        carbon_logger.debug(f"LED bulb runtime (readable): {self.led_bulb_runtime}")

    def calculate_smartwatch_runtime(self) -> None:
        """
        Calculate the runtime of a smartwatch

        returns: None
        """
        # I cannot find a source for this but looking at online articles such as
        # https://www.stuff.tv/review/samsung-galaxy-watch-6-classic-review/
        # https://www.knowyourmobile.com/wearable-technology/apple-watch-battery-comparison-chart-size-battery-life-and-charge-time/
        # We can estimate based on the battery capacity and the claimed battery life
        # Apple watch Ultra 300mAh to 540mAh for the biggest most expensive model 18-36 hours
        # Samsung galaxy watch 300mAh to 425mAh up to 30 hours
        # So lets say 350mAh battery and 20 hours battery life since you do need to charge these things daily
        # Battery(Wh) = Battery(mAh) * Voltage
        # Average draw = Battery(Wh) / Battery Life
        # so lets say 350mAh * 3.7V = 1.29Wh | 1.29Wh / 20 hours = 0.06W
        # Based on the articles this suggests idle power consumption
        # Normal use around 0.2W to 0.5W so lets do higher end just for comparison
        power_use_idle = 0.06  # watts
        power_use_normal = 0.5  # watts
        smartwatch_runtime_seconds_idle = (
            self.energy_consumed_wh * 3600
        ) / power_use_idle
        smartwatch_runtime_seconds_normal = (
            self.energy_consumed_wh * 3600
        ) / power_use_normal
        self.smartwatch_runtime_idle = self._convert_seconds_to_readable(
            smartwatch_runtime_seconds_idle
        )
        self.smartwatch_runtime_normal = self._convert_seconds_to_readable(
            smartwatch_runtime_seconds_normal
        )

        carbon_logger.debug(f"Smartwatch runtime (readable): {self.smartwatch_runtime_idle}")
        carbon_logger.debug(
            f"Smartwatch runtime normal use (readable): {self.smartwatch_runtime_normal}"
        )

    def to_html(self, template_path: str = "./energy.html") -> str:
        """
        Format the calculated values into an HTML template

        args:
            template_path (str): Path to the HTML template file

        returns: str
        """
        with open(template_path, "r") as file:
            html_template = file.read()

        html_output = html_template.replace(
            "{{ rover_distance }}", f"{self.rover_distance_covered:.2f}"
        )
        html_output = html_output.replace("{{ led_bulb }}", self.led_bulb_runtime)
        html_output = html_output.replace(
            "{{ smartwatch_runtime_idle }}", self.smartwatch_runtime_idle
        )
        html_output = html_output.replace(
            "{{ smartwatch_runtime_normal }}", self.smartwatch_runtime_normal
        )

        return html_output


def calculate_emission_equivalents(
    file_path: str = "./emissions.csv",
    template_path: str = "../energy.html",
    debug: bool = False,
    experiment_id: int = None,
) -> None:
    """
    args:
        file_path (str): Path to the codecarbon emissions CSV file
        template_path (str): Path to the HTML template file
        debug (bool): Enable debug carbon_logger
        experiment_id (int): Filter data by experiment ID

    returns: None
    """
    if debug:
        carbon_logger.basicConfig(level=carbon_logger.DEBUG)
    else:
        carbon_logger.basicConfig(level=carbon_logger.INFO)

    try:
        df = pd.read_csv(file_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        if experiment_id is not None:
            df = df[df["experiment_id"].astype(str) == str(experiment_id)]
            if df.empty:
                carbon_logger.error(f"No data found for experiment_id: {experiment_id}")
                return None

        latest_run = df.sort_values(by="timestamp", ascending=False).iloc[0]
    except Exception as e:
        carbon_logger.error(f"Error reading data: {e}")
        return None

    # Total energy consumed in kWh
    energy_consumed_kwh = latest_run["energy_consumed"]
    if energy_consumed_kwh <= 0:
        carbon_logger.error(f"Invalid energy consumption value: {energy_consumed_kwh}")
    else:
        carbon_logger.debug(f"Energy consumed (kWh): {energy_consumed_kwh}")

    energy_consumption = EnergyConsumption(energy_consumed_kwh)

    try:
        energy_consumption.calculate_rover_distance()
        energy_consumption.calculate_led_bulb_runtime()
        energy_consumption.calculate_smartwatch_runtime()
    except Exception as e:
        carbon_logger.error(f"Error calculating energy consumption: {e}")
        return None

    html_output = energy_consumption.to_html(template_path)
    display(HTML(html_output))
