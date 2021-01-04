import boto3
import time
from app import manager
from app.form import autoscalingForm
from sqlalchemy import desc

# Loop to check the average CUP utilization every minute
def auto_handler():
    print("Auto scaling is activated")

    config = autoscalingForm.query.order_by(desc(autoscalingForm.id)).first()
    threshold_max = config.threshold_max
    threshold_min = config.threshold_min
    ratio_expand = config.ratio_expand
    ratio_shrink = config.ratio_shrink
    if threshold_max == '' or float(threshold_max) <= 0:
        threshold_max = 80
    if threshold_min == '':
        threshold_min = 10
    if ratio_expand == '' or float(ratio_expand) <= 0:
        ratio_expand = 2
    if ratio_shrink == '' or float(ratio_shrink) <= 0:
        ratio_shrink = 0.5

    print("Threshold_max is {}, threshold_min is {}, ratio_expand is {}, ratio_shrink is {}.".format(str(threshold_max),
                                                                                                     str(threshold_min),
                                                                                                     str(ratio_expand),
                                                                                                     str(ratio_shrink)))
    ec2 = boto3.resource('ec2')
    if(manager.compare_inst()):
        instances = manager.select_running_inst()  # Get running and healthy instances
        instance_id, average_uti = manager.average_CPU_uti(instances)
        print('Average CPU utilization is: ', average_uti)
        manager.full_load_check(instance_id)  # Load checking, full load is 8 workers, minimum load is 1 worker

        # Average CPU utilization is larger maximum threshold value,then add instances
        if average_uti > threshold_max and len(instance_id) < 8:
            # Number of instance to create
            new_inst_num = int(len(instance_id) * (float(ratio_expand) - 1))

            if (len(instance_id) + new_inst_num) > 8:   # Maximum number of workers is 8
                new_inst_num = 8 - len(instance_id)
            print('Auto adding ', new_inst_num, 'new instances')

            for i in range(new_inst_num):
                manager.inst_add()

        # Average CPU is smaller minimum threshold value, then reduce instances
        if average_uti < threshold_min and len(instance_id) > 1:
            # Number of instances to delete
            remove_inst_num = int(len(instance_id) * (1 - float(ratio_shrink)))
            if len(instance_id) - int(remove_inst_num) == 0:
                remove_inst_num = 1
            print('Auto terminating ', remove_inst_num, 'instances')

            if remove_inst_num > 0 and (len(instance_id) - remove_inst_num) >= 1: # Minimum number of workers is 1
                id_to_remove = instance_id[:remove_inst_num]
                print('IDs of the instances to be removed: ', id_to_remove)

                for id in id_to_remove:
                    manager.inst_remove(id)
    else:
        print('Stopped Auto Scaling!')
        return


