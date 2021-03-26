import argparse
import os

import random
import shutil
import warnings
import sys

warnings.filterwarnings("ignore")

from keras import backend as K
import numpy as np
from PIL import Image, ImageFilter
from skimage.measure import compare_ssim as SSIM
import keras
from util import get_model

import tensorflow as tf
import os
import prettytable as pt
from attack import gen_adv_data

BIM = "bim"
CW = "cw"
FGSM = "fgsm"
JSMA = "jsma"
PGD = "pgd"
APGD = "apgd"
DF = "deepfool"
NF = "newtonfool"
SA = "squareattack"
ST = "spatialtransformation"
ATTACK_NAMES = [APGD, BIM, CW, DF, FGSM, JSMA, NF, PGD, SA, ST]
DATA_DIR = "../data/"
MODEL_DIR = "../models/"


####for solving some specific problems, don't care
config = tf.ConfigProto()
config.gpu_options.allow_growth = True
sess = tf.Session(config=config)

# the data is in range(-.5, .5)
def load_data(dataset_name):
    assert (dataset_name.upper() in ['MNIST', 'CIFAR', 'SVHN'])
    dataset_name = dataset_name.lower()
    x_train = np.load(DATA_DIR + dataset_name + '/benign/x_train.npy')
    y_train = np.load(DATA_DIR + dataset_name + '/benign/y_train.npy')
    x_test = np.load(DATA_DIR + dataset_name + '/benign/x_test.npy')
    y_test = np.load(DATA_DIR + dataset_name + '/benign/y_test.npy')
    return x_train, y_train, x_test, y_test

class AttackEvaluate:
    # model does not have softmax layer
    def __init__(self, model, ori_x, ori_y, adv_x):
        self.model = model
        # get the raw data
        self.nature_samples = ori_x
        self.labels_samples = ori_y
        # get the adversarial examples
        self.adv_samples = adv_x
        # self.adv_labels = np.load('{}{}_AdvLabels.npy'.format(self.AdvExamplesDir, self.AttackName))

        predictions = model.predict(self.adv_samples)

        def soft_max(x):
            return np.exp(x) / np.sum(np.exp(x), axis=0)

        tmp_soft_max = []
        for i in range(len(predictions)):
            tmp_soft_max.append(soft_max(predictions[i]))

        self.softmax_prediction = np.array(tmp_soft_max)

    # help function
    def successful(self, adv_softmax_preds, nature_true_preds):
        if np.argmax(adv_softmax_preds) != np.argmax(nature_true_preds):
            return True
        else:
            return False

    # 1 MR:Misclassification Rate
    def misclassification_rate(self):

        cnt = 0
        for i in range(len(self.adv_samples)):
            if self.successful(adv_softmax_preds=self.softmax_prediction[i], nature_true_preds=self.labels_samples[i]):
                cnt += 1
        mr = cnt / len(self.adv_samples)
        print('MR:\t\t{:.1f}%'.format(mr * 100))
        return mr



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='MR and Linf')
    parser.add_argument('-dataset', help="dataset to use", choices=['mnist', 'cifar', 'svhn'])
    parser.add_argument('-model', help="target model to attack",
                        choices=['vgg16', 'resnet20', 'lenet1', 'lenet4', 'lenet5', 'svhn_model',
                                 'svhn_first', 'svhn_second'])
    args = parser.parse_args()

    # dataset = args.dataset
    # model_name = args.model
    # attack = 'PGD'

    datasets = ['cifar', 'mnist', 'svhn'] #, 
    model_dict = {
                'mnist': ['lenet1', 'lenet4', 'lenet5'], #, 'lenet4', 'lenet5'
                'cifar': ['vgg16'], # , 'resnet20'
                'svhn' : ['svhn_model', 'svhn_second', 'svhn_first']
                }

    defense_names = ['Benign', 'DeepHunter'] # , 'DeepHunter'
    optim_defenses = [FGSM, PGD]

    attack_names = ['Benign', 'DeepHunter']
    optim_attacks = [FGSM, PGD]

    table = pt.PrettyTable()
    table.field_names = ["Dataset", "Model"] + attack_names + optim_attacks
    ### Set align
    for field_name in ["Dataset", "Model"] + attack_names + optim_attacks:
        table.align[field_name] = 'l'


    for dataset in datasets:
        for model_name in model_dict[dataset]:

            '''Load models for denfense'''
            from keras.models import load_model

            model_defenses = {}
            for defense in defense_names + optim_defenses:
                # To-Do: to be modified after we generate using new paths.    
                if defense == 'Benign':
                    ### load benign model
                    model_defenses[defense] = load_model("{}{}/{}.h5".format(MODEL_DIR, dataset, model_name))
                elif defense == 'DeepHunter':
                    ### load deephunter model
                    model_defenses[defense] = load_model('new_model/dp_{}.h5'.format(model_name))
                else:
                    #### load models trained with optimization-based attack
                    model_path = "{}{}/{}".format(MODEL_DIR, dataset, 'adv_' + model_name + '_' + defense + '.h5')
                    model_defenses[defense] = load_model(model_path)


            '''Load dataset'''
            x_adv_attacks = {}
            for attack in attack_names:
                # To-Do: to be modified after we generate using new paths.
                if attack == 'Benign':
                    ### benign dataset
                    x_train, y_train, x_test, y_test = load_data(dataset)
                    x_adv_attacks[attack] = x_test
                elif attack == 'DeepHunter':
                    ### deephunter dataset
                    adv_dir = "{}{}/adv/{}/{}/".format(DATA_DIR, dataset, model_name, 'deephunter')
                    dp_adv_path = "{}deephunter_adv_test.npy".format(adv_dir)
                    x_adv_attacks[attack] = np.load(dp_adv_path)
                else:
                    pass

            '''Computing accuracy'''

            ### get Benign data
            defense = 'Benign'
            begign_content = {}
            for attack in attack_names + optim_attacks:
                if  (attack in optim_attacks):
                    # generate adv examples
                    adv_examples = gen_adv_data(model_defenses[defense], x_test, y_test, attack, dataset, 256)
                elif (attack in attack_names):
                    adv_examples = x_adv_attacks[attack]


                criteria = AttackEvaluate(model_defenses[defense], x_test, y_test, adv_examples)
                accuracy = 1 - criteria.misclassification_rate()
                begign_content[attack] = accuracy

            for defense in defense_names + optim_defenses:
                # if defense == 'Benign':
                #     continue # don't show data for original model
                row_content = [dataset, model_name + '_' + defense]
                for attack in attack_names + optim_attacks:
                    if  (attack in optim_attacks):
                        # generate adv examples
                        adv_examples = gen_adv_data(model_defenses[defense], x_test, y_test, attack, dataset, 256)
                    elif (attack in attack_names):
                        adv_examples = x_adv_attacks[attack]

                    criteria = AttackEvaluate(model_defenses[defense], x_test, y_test, adv_examples)
                    accuracy = 1 - criteria.misclassification_rate()
                    difference = accuracy - begign_content[attack]

                    row_content.append(str(round(accuracy * 100,2)) + 
                                        '(' + str(round(difference * 100,2)) + ')')
                
                table.add_row(row_content)
            
            
            
            print(table)

