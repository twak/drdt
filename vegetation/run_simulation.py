from api.utils import Postgres
import os
from random import randrange
import random
from datetime import timedelta, datetime
import integrate_path
import grow_trees

experiment="_1"

work_dir = "/home/twak/Downloads/vege_scratch"
report_folder=f"/home/twak/Downloads/vege_sim{experiment}"
las_table="scenario.fred_vege_a14_las_chunks"
grow_folder=f"experiment{experiment}/grown_las/"
prune_folder=f"experiment{experiment}/pruned_las/"
scenario_credentials = "fred.json"
scenario_api_key = "f8c82b4e8156eef1c7a2f24dfd46196a"

def random_date(start, end): #https://stackoverflow.com/questions/553303/how-to-generate-a-random-date-between-two-other-dates

    delta = end - start
    int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
    random_second = randrange(int_delta)
    return start + timedelta(seconds=random_second)


def do_inspect(today, id, previous_date, inspector_id):

    print(f"\n\n ** inspecting {id}")

    if random.random() < 0.2:
        return False

    global las_table, grow_folder, work_dir, scenario_credentials
    # grow_trees.grow_trees_on(id, today.strftime(utils.time_to_sql), las_table)
    grow_trees.grow_trees_on(id, today, las_table=las_table, grown_route=grow_folder, trees_per_meter=0.01)

    ip = integrate_path.IntegratePath(id)
    ip.las_table = las_table
    ip.scenario_credentials = scenario_credentials
    ip.scenario_api_key = scenario_api_key
    ip.do_integral_vert = ip.do_integral_horiz = True
    ip.report_path = f"{report_folder}/{today}_inspect_{id}"
    ip.work_dir = work_dir
    ip.report_type = "Inspection"
    ip.date = today
    ip.go()

    return True

def do_prune(today, id, previous_date, pruner_id):

    print(f"\n\n ** pruning {id}")

    if random.random() < 0.2:
        return None

    today = today + timedelta(hours=1)  # prune after growing

    prune = integrate_path.IntegratePath(id) # do the pruning
    prune.las_table = las_table
    prune.scenario_api_key = scenario_api_key
    prune.do_write_pruned_las = True
    prune.las_write_location = prune_folder
    prune.work_dir = work_dir
    prune.date = today
    prune.go()

    today = today + timedelta(hours=1)  # scan after pruning

    prune.do_integral_vert = prune.do_integral_horiz = True # do the report
    prune.do_write_pruned_las = False
    prune.report_path = f"{report_folder}/{today}_prune_{id}"
    prune.report_type = "Post-Prune Report"
    prune.date = today
    prune.go()


    return prune.pruned_volume

def run_simulation (days = 10):

    os.makedirs(report_folder, exist_ok=True)

    # reset the lidar database table
    with Postgres(pass_file="fred.json") as pg:
        pg.cur.execute(f"""
            delete from {las_table}
        """)

    with Postgres() as pg:
        pg.cur.execute(f"""
            SELECT id, geom, geom_z
            FROM public.a14_vegetation_segments
            """)

        last_inspection = [] # we prioritise segments with higher volume
        volume = []

        start_date = datetime.strptime('14/10/2024 09:00', '%d/%m/%Y %H:%M')
        old_date   = datetime.strptime('01/10/2021 00:00', '%d/%m/%Y %H:%M')

        # initialise each segment's volume randomly
        for results in pg.cur.fetchall():
            last_inspection.append ([results[0],  random_date(old_date, start_date)])
            volume.append([results[0], random.randint(0, 100)])

        # loop over the days of the simulation
        for day in range(0,days):

            today = start_date + timedelta(days=day)
            print ( f"\n\n simulating {today}" )

            # simulate the inspection
            last_inspection.sort(key=lambda x: x[1])
            for inspector in range(0,random.randint(0, 5) ):
                if do_inspect(today, last_inspection[inspector][0], last_inspection[inspector][1], inspector):
                    last_inspection[inspector][1] = today # inpection was complete


            # simulate the pruning
            volume.sort(key=lambda x: x[1])
            for pruner in range ( 0,random.randint(1, 2) ):
                result = do_prune(today, last_inspection[pruner][0], last_inspection[pruner][1], pruner)
                if result:
                    volume[pruner][1] = result



if __name__ == '__main__':
    random.seed(123)
    run_simulation()