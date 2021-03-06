import numpy as np
import subprocess
import fileinput
import argparse
import random
import shutil
import math
import cv2
import os
import sys

global counter

def createNumpyMatrix(geometricVertices):
    """Parse the strings from the obj file and convert them into numpy matrix of floats to perform math efficiently"""
    vertices = []
    for line in geometricVertices:
        # convert the string to floats for x,y,z coordinates
        elements = list(map(lambda x: float(x), line.split()[1:]))
        vertices.append(elements)

    # convert to 3 x numPoints matrix
    vertices = np.asarray(vertices)
    vertices = vertices.T
    #print(vertices.shape)

    return vertices

def getCenterOfMass(geometricVertices):
    # com will be a 3x1 vector
    com = np.average(geometricVertices, axis=1)
    com = com.reshape(3,1)

    return com

def centerAndScaleObject(geometricVertices, com, resize, meshIsAreaLight):
    """Translate the object vertices so that they are centered around the origin"""
    geometricVertices = geometricVertices - com

    stdev = np.std(geometricVertices, axis=1) / float(resize)
    stdev = stdev.reshape(3,1)

    if not meshIsAreaLight:
        # do not scale the area light mesh object
        geometricVertices = geometricVertices / stdev

    return geometricVertices

def getRotationMatrix(angleX=0.0, angleY=0.0, angleZ=0.0):
    if angleX == 0.0 and angleY == 0.0 and angleZ == 0.0:
        angleX = round(random.uniform(0, 2*math.pi), 2)
        angleY = round(random.uniform(0, 2*math.pi), 2)
        angleZ = round(random.uniform(0, 2*math.pi), 2)

    Rx = np.array([[1, 0, 0], [0, math.cos(angleX), -math.sin(angleX)], [0, math.sin(angleX), math.cos(angleX)]], dtype=np.float)
    Ry = np.array([[math.cos(angleY), 0, math.sin(angleY)], [0, 1, 0], [-math.sin(angleY), 0, math.cos(angleY)]], dtype=np.float)
    Rz = np.array([[math.cos(angleZ), -math.sin(angleZ), 0], [math.sin(angleZ), math.cos(angleZ), 0], [0, 0, 1]], dtype=np.float)

    R = np.matmul(np.matmul(Rx, Ry), Rz)
    #R = np.identity(3)
    return R

def rotateObject(geometricVertices, rotationMatrix):
    """Perform matrix multiplication - Rx to get the vertex coordinates after rotation"""
    rotatedGeometricVertices = np.matmul(rotationMatrix, geometricVertices)

    return rotatedGeometricVertices

def getAxisAlignedBoundingBox(geometricVertices):
    mins = np.amin(geometricVertices, axis=1)
    maxs = np.amax(geometricVertices, axis=1)

    # bbox will have 6 elements
    # xLeft, xRight, yTop, yBottom, zNear, zFar
    bbox = {'xmin':mins[0], 'xmax':maxs[0], 'ymin':mins[1], 'ymax':maxs[1], 'zmin':mins[2], 'zmax':maxs[2]}
    #print("bounding box:", bbox)

    return bbox

def positionObjectInTheBox(geometricVertices, bbox, com):
    """Calculate the bounds of the places where the object can be placed inside the box scene and place the object there"""
    # assumption - the object can fit inside the box scene entirely
    # the scaling to have 5 units standard deviation is just for that

    # create the range tuple in which com of object can lie - (min, max)
    xComRange = (-10.0 - bbox['xmin'], 10.0 - bbox['xmax'])
    yComRange = (-10.0 - bbox['ymin'], 10.0 - bbox['ymax'])
    zComRange = (20.0 - bbox['zmin'], 30.0 - bbox['zmax'])

    # skip this object if it does not fit inside the box scene
    if (xComRange[0] > xComRange[1]) or (yComRange[0] > yComRange[1]) or (zComRange[0] > zComRange[1]):
        print("\n\nMisfit\n\n")
        return geometricVertices, False

    # generate the position - (x,y,z) for the com of the object within the above computed range
    # assume uniform distribution
    x = round(random.uniform(xComRange[0], xComRange[1]), 2)
    y = round(random.uniform(yComRange[0], yComRange[1]), 2)
    z = round(random.uniform(zComRange[0], zComRange[1]), 2)

    # translate the object so that it is now located at the above randomly generated location
    newCom = np.array([x,y,z]).reshape(3,1)
    #newCom = np.array([0,0,25]).reshape(3,1)
    geometricVertices = geometricVertices + newCom

    return geometricVertices, True

def positionLightInTheBox(geometricVertices, bbox, com):
    # create the range tuple in which com of object can lie - (min, max)
    xComRange = (-10.0 - bbox['xmin'], 10.0 - bbox['xmax'])
    yComRange = (-10.0 - bbox['ymin'], 10.0 - bbox['ymax'])
    zComRange = (20.0 - bbox['zmin'], 30.0 - bbox['zmax'])

    # skip this object if it does not fit inside the box scene
    if (xComRange[0] > xComRange[1]) or (yComRange[0] > yComRange[1]) or (zComRange[0] > zComRange[1]):
        return geometricVertices, False

    # generate the position - (x,y,z) for the com of the object within the above computed range
    # assume uniform distribution
    x = round(random.uniform(xComRange[0], xComRange[1]), 2)
    y = 9.5 # do not change y, the area light has to remain on the ceiling only
    z = round(random.uniform(zComRange[0], zComRange[1]), 2)

    # translate the object so that it is now located at the above randomly generated location
    newCom = np.array([x,y,z]).reshape(3,1)
    #newCom = np.array([0,-5,25]).reshape(3,1)
    geometricVertices = geometricVertices + newCom

    return geometricVertices

def npMatrixToStrings(geometricVertices, dataType):
    stringList = []
    if dataType == 'geometricVertices':
        label = 'v '
    else:
        # we are modifying vertex normals
        label = 'vn '

    for vertex in geometricVertices.T:
        line = label + str(vertex[0]) + " " + str(vertex[1]) + " " + str(vertex[2]) + "\n"
        stringList.append(line)

    return stringList

def removeTextureVertices(faces):
    newFaces = []
    for line in faces:
        elements = line.split()[1:]
        # elements = ['f', 'v/vt/vn', 'v/vt/vn', 'v/vt/vn']
        # elements = ['f', '1231/14134/2341', '12/24/432', '342/345/67']
        # we want following
        # elements = ['f', '1231/14134/2341', '12/24/432', '342/345/67']
        for index, face in enumerate(elements):
            #startIndex = face.find('/')
            #endIndex = face.rfind('/')+1
            endIndex = face.rfind('/')
            #toReplace = face[startIndex:endIndex]
            #face = face.replace(toReplace, "//")
            face = face[:endIndex]

            elements[index] = face

        newLine = 'f ' + elements[0] + " " + elements[1] + " " + elements[2] + "\n"
        newFaces.append(newLine)

    return newFaces

def removeVertexNormals(faces):
    newFaces = []
    for line in faces:
        elements = line.split()[1:]
        # elements = ['f', 'v/vt/vn', 'v/vt/vn', 'v/vt/vn']
        # elements = ['f', '1231/14134/2341', '12/24/432', '342/345/67']
        # we want following
        # elements = ['f', '1231/14134', '12/24', '342/345']
        for index, face in enumerate(elements):
            endIndex = face.rfind('/')
            face = face[:endIndex]

            elements[index] = face

        newLine = 'f ' + elements[0] + " " + elements[1] + " " + elements[2] + "\n"
        newFaces.append(newLine)

    return newFaces

def printFirstThreeVertices(geometricVertices):
    print(len(geometricVertices))
    for i in range(6):
        print(geometricVertices.T[i])
        #print(geometricVertices[i])

def renderImages(lightType):
    if lightType == 'point':
        subprocess.run(["nori.exe", "custom_simple.xml"])
        subprocess.run(["nori.exe", "custom_light_point.xml"])
        ##subprocess.run(["nori.exe", "custom_depth_point.xml"])
        subprocess.run(["nori.exe", "custom_noShadow_point.xml"])
    else:
        subprocess.run(["nori.exe", "custom_whitted.xml"])
        subprocess.run(["nori.exe", "custom_light.xml"])
        subprocess.run(["nori.exe", "custom_depth.xml"])
        subprocess.run(["nori.exe", "custom_noShadow.xml"])

def alignImages(dstFolder, fileName):
    global counter
    # these weird names can be changed if nori.exe is updated :)
    # it was helpful when there was only one xml file
    noShadowImage = cv2.imread('custom_noShadow_point_noShadows.png', cv2.IMREAD_COLOR)
    #depthMapImage = cv2.imread('custom_depth_point_depthMap.png', cv2.IMREAD_COLOR)
    depthMapImage0 = cv2.imread('8viewDepthMap_0.png', cv2.IMREAD_COLOR)
    depthMapImage1 = cv2.imread('8viewDepthMap_1.png', cv2.IMREAD_COLOR)
    depthMapImage2 = cv2.imread('8viewDepthMap_2.png', cv2.IMREAD_COLOR)
    depthMapImage3 = cv2.imread('8viewDepthMap_3.png', cv2.IMREAD_COLOR)
    depthMapImage4 = cv2.imread('8viewDepthMap_4.png', cv2.IMREAD_COLOR)
    depthMapImage5 = cv2.imread('8viewDepthMap_5.png', cv2.IMREAD_COLOR)
    depthMapImage6 = cv2.imread('8viewDepthMap_6.png', cv2.IMREAD_COLOR)
    depthMapImage7 = cv2.imread('8viewDepthMap_7.png', cv2.IMREAD_COLOR)

    lightMapImage = cv2.imread('custom_light_point_lightDepth.png', cv2.IMREAD_COLOR)
    groundTruthImage = cv2.imread('custom_simple_simple.png', cv2.IMREAD_COLOR)

    if lightType == 'area':
        noShadowImage = cv2.imread('custom_noShadow.png', cv2.IMREAD_COLOR)
        depthMapImage = cv2.imread('custom_depth.png', cv2.IMREAD_COLOR)
        lightMapImage = cv2.imread('custom_light.png', cv2.IMREAD_COLOR)
        groundTruthImage = cv2.imread('custom_whitted.png', cv2.IMREAD_COLOR)

    alignedImage = np.concatenate((noShadowImage, lightMapImage, depthMapImage0, depthMapImage1, depthMapImage2, depthMapImage3, depthMapImage4, depthMapImage5, depthMapImage6, depthMapImage7, groundTruthImage), axis=1)
    cv2.imwrite(os.path.join(dstFolder, fileName + '_' + str(counter).zfill(4) + '.png'), alignedImage)
    counter += 1
    #cv2.imwrite(os.path.join(dstFolder, fileName + '.png'), groundTruthImage)

def randomChooseK(inList, k):
    retList = []
    for i in range(k):
        index = random.choice(range(len(inList)))
        retList.append(inList.pop(index))

    return retList

def splitImages(dstFolder, valCount, testCount, alignedImages):
    os.mkdir(os.path.join(dstFolder, 'train'))
    os.mkdir(os.path.join(dstFolder, 'test'))
    os.mkdir(os.path.join(dstFolder, 'val'))

    # randomly choose images for validation set
    valAlignedImages = randomChooseK(alignedImages, valCount)
    # now randomly choose images for test set
    testAlignedImages = randomChooseK(alignedImages, testCount)
    # remaining images go in train set
    trainAlignedImages = alignedImages

    # move the images to their respective folders
    for index, imagePath in enumerate(valAlignedImages):
    	shutil.move(imagePath, os.path.join(dstFolder, os.path.join('val', str(index) + '.png')))
    for index, imagePath in enumerate(testAlignedImages):
    	shutil.move(imagePath, os.path.join(dstFolder, os.path.join('test', str(index) + '.png')))
    for index, imagePath in enumerate(trainAlignedImages):
    	shutil.move(imagePath, os.path.join(dstFolder, os.path.join('train', str(index) + '.png')))


def randomizeObject(meshFile, resize, meshIsAreaLight=False):
    fileName = meshFile
    objFile = open(fileName, 'r')
    # sort all the strings in their corresponding lists
    textureVertices = []
    geometricVertices = []
    vertexNormals = []
    faces = []
    for line in objFile:
        if line[:2] == 'vt':
            # texture vertices
            textureVertices.append(line)
        elif line[:2] == 'vn':
            # vertex normals
            vertexNormals.append(line)
        elif line[0] == 'v':
            # geometricVertices
            geometricVertices.append(line)
        elif line[0] == 'f':
            # faces
            faces.append(line)
        else:
            continue
    objFile.close()

    # create numpy matrix from the vertices string
    geometricVertices = createNumpyMatrix(geometricVertices)

    # compute the center of mass of the geometric vertices matrix
    com = getCenterOfMass(geometricVertices)

    # arrange the vertices around the center of mass
    # scale the object so that its vertices have 2 units standard deviation from the mean
    geometricVertices = centerAndScaleObject(geometricVertices, com, resize, meshIsAreaLight)

    if not meshIsAreaLight:
        # ROTATION SHOULD HAPPEN AFTER CENTERING AND SCALING THE OBJECT AND BEFORE TRANSLATING IT
        # TO ITS NEW POSITION, IT BECOMES EASIER THAT WAY
        # create rotation matrix if needed
        rotationMatrix = getRotationMatrix()

        # rotate the object
        geometricVertices = rotateObject(geometricVertices, rotationMatrix)
        # CAUTION! MIGHT NEED TO CHANGE THE VERTEX NORMALS TOO
        # it probably was causing problems, so also rotating the vertex normals now!
        vertexNormals = createNumpyMatrix(vertexNormals)
        vertexNormals = rotateObject(vertexNormals, rotationMatrix)

    # get axis aligned bounding box of the object
    bbox = getAxisAlignedBoundingBox(geometricVertices)
    # bbox will have 6 elements
    # xLeft, xRight, yTop, yBottom, zNear, zFar

    bRenderImage = True
    if not meshIsAreaLight:
        # translate the object to position it SOMEWHERE in the box scene
        geometricVertices, bRenderImage = positionObjectInTheBox(geometricVertices, bbox, com)
    else:
        # translate the area light to some position outside the box
        geometricVertices = positionLightInTheBox(geometricVertices, bbox, com)

    # if object cannot be positioned in the box, skip it, do not render that image
    if not bRenderImage:
        return bRenderImage

    # convert the modified geometricVertices back to strings
    geometricVertices = npMatrixToStrings(geometricVertices, 'geometricVertices')

    if not meshIsAreaLight:
        # convert the modified vertexNormals back to strings
        vertexNormals = npMatrixToStrings(vertexNormals, 'vertexNormals')

    # remove texture vertices information from faces list
    faces = removeVertexNormals(faces)
    faces = removeTextureVertices(faces)

    # create a temporary obj file for the modified object
    if meshIsAreaLight:
        fileName = 'tempLight.obj'
    else:
        fileName = 'tempMesh.obj'

    objFile = open(fileName, 'w')
    # write the geometric vertices to file first up
    for line in geometricVertices:
        objFile.write(line)
    # next fill up the texture vertices
    objFile.write("\n")
    #for line in textureVertices:
    #    objFile.write(line)
    # next fill up the vertex normals
    objFile.write("\n")
    #for line in vertexNormals:
    #    objFile.write(line)
    # next fill up the faces
    objFile.write("\n")
    for line in faces:
        objFile.write(line)

    objFile.close()

    return bRenderImage


def put_rand_light_pos(random_pos_str, xml_file_name):
    for line in fileinput.input(xml_file_name, inplace=1):
        # if current line has string 'position' in it, then replace line with string that contains random light position
        if 'position' in line:
            line = random_pos_str + '\n'
        # add current line to file. (only file that contains string 'position' is changed
        sys.stdout.write(line)


def randomizeLight(lightType):
    # use randomizeObject if we are using area light (need to skip rotations in this case)
    if lightType == 'area':
        lightMeshObj = './light.obj'  # is this the right path to give to randomizeObject? yes it is!
        randomizeObject(lightMeshObj, resize=1, meshIsAreaLight=True)
        return
        
    # we only get to this point if we are dealing with a point light
    # pick 3 random points in the following intervals and change light position in xml file
    scene_min_x = -10
    scene_max_x = 10
    scene_min_y = -10
    scene_max_y = 10
    scene_min_z = 10
    scene_max_z = 20  # with these z bounderies, the light will only be outside box (in respect to z axis)
    d = 1  # don't want light exactly on edge of box
    randX = random.uniform(scene_min_x + d, scene_max_x - d)
    randY = random.uniform(scene_min_y + d, scene_max_y - d)
    randZ = random.uniform(scene_min_z + d, scene_max_z - d)

    rand_pos = str(randX) + "," + str(randY) + "," + str(randZ)
    random_pos_str = "<point name=\"position\" value=\"" + rand_pos + "\"/>"

    put_rand_light_pos(random_pos_str, 'custom_simple.xml')
    put_rand_light_pos(random_pos_str, 'custom_depth_point.xml')
    put_rand_light_pos(random_pos_str, 'custom_light_point.xml')
    put_rand_light_pos(random_pos_str, 'custom_noShadow_point.xml')

def get8Views(meshFile):
    if os.path.exists('8viewDepthMap_0.png'):
        os.remove('8viewDepthMap_0.png')
    if os.path.exists('8viewDepthMap_1.png'):
        os.remove('8viewDepthMap_1.png')
    if os.path.exists('8viewDepthMap_2.png'):
        os.remove('8viewDepthMap_2.png')
    if os.path.exists('8viewDepthMap_3.png'):
        os.remove('8viewDepthMap_3.png')
    if os.path.exists('8viewDepthMap_4.png'):
        os.remove('8viewDepthMap_4.png')
    if os.path.exists('8viewDepthMap_5.png'):
        os.remove('8viewDepthMap_5.png')
    if os.path.exists('8viewDepthMap_6.png'):
        os.remove('8viewDepthMap_6.png')
    if os.path.exists('8viewDepthMap_7.png'):
        os.remove('8viewDepthMap_7.png')

    views = [(math.pi/4, math.pi/4), (math.pi/4, -math.pi/4), (math.pi/4, 3*math.pi/4), (math.pi/4, -3*math.pi/4),
            (-math.pi/4, math.pi/4), (-math.pi/4, -math.pi/4), (-math.pi/4, 3*math.pi/4), (-math.pi/4, -3*math.pi/4)]

    for index, view in enumerate(views):
        fileName = meshFile
        objFile = open(fileName, 'r')
        # sort all the strings in their corresponding lists
        textureVertices = []
        geometricVertices = []
        vertexNormals = []
        faces = []
        for line in objFile:
            if line[:2] == 'vt':
                # texture vertices
                textureVertices.append(line)
            elif line[:2] == 'vn':
                # vertex normals
                vertexNormals.append(line)
            elif line[0] == 'v':
                # geometricVertices
                geometricVertices.append(line)
            elif line[0] == 'f':
                # faces
                faces.append(line)
            else:
                continue
        objFile.close()

        # create numpy matrix from the vertices string
        geometricVertices = createNumpyMatrix(geometricVertices)

        # compute the center of mass of the geometric vertices matrix
        com = getCenterOfMass(geometricVertices)

        # arrange the vertices around the center of mass
        # scale the object so that its vertices have 2 units standard deviation from the mean
        geometricVertices = centerAndScaleObject(geometricVertices, com, resize, meshIsAreaLight=False)

        rotationMatrix = getRotationMatrix(angleX=view[0], angleY=view[1], angleZ=0)
        # rotate the object
        geometricVertices = rotateObject(geometricVertices, rotationMatrix)
        # CAUTION! MIGHT NEED TO CHANGE THE VERTEX NORMALS TOO
        # it probably was causing problems, so also rotating the vertex normals now!
        vertexNormals = createNumpyMatrix(vertexNormals)
        vertexNormals = rotateObject(vertexNormals, rotationMatrix)

        # position object in center of scene - this scene has no box
        geometricVertices += np.array([0,0,25]).reshape(3,1)

        # convert the modified geometricVertices back to strings
        geometricVertices = npMatrixToStrings(geometricVertices, 'geometricVertices')

        # convert the modified vertexNormals back to strings
        vertexNormals = npMatrixToStrings(vertexNormals, 'vertexNormals')

        # remove texture vertices information from faces list
        faces = removeVertexNormals(faces)
        faces = removeTextureVertices(faces)

        # create a temporary obj file for the modified object
        fileName = 'tempMesh.obj'

        objFile = open(fileName, 'w')
        # write the geometric vertices to file first up
        for line in geometricVertices:
            objFile.write(line)
        # next fill up the texture vertices
        objFile.write("\n")
        #for line in textureVertices:
        #    objFile.write(line)
        # next fill up the vertex normals
        objFile.write("\n")
        #for line in vertexNormals:
        #    objFile.write(line)
        # next fill up the faces
        objFile.write("\n")
        for line in faces:
            objFile.write(line)

        objFile.close()

        # render the depthmap
        subprocess.run(["nori.exe", "custom_8view_depth.xml"])

        os.rename('custom_8view_depth_depthMap.png', '8viewDepthMap_' + str(index) + '.png')



if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Data generator")
    parser.add_argument('-mesh', '--mesh_folder_path', required=True, help="Path to meshes folder")
    parser.add_argument('-light', '--lightType', required=True, help="Light type: 'point' or 'area'")
    parser.add_argument('-dst', '--dst_folder_path', required=True, help="Folder name where aligned images are to be saved")
    parser.add_argument('-val', type=int, required=True, help="Percentage of images in validation set")
    parser.add_argument('-test', type=int, required=True, help="Percentage of images in test set")
    
    args = parser.parse_args()    
    meshFolder = args.mesh_folder_path
    lightType = args.lightType
    dstFolder = args.dst_folder_path
    valPercentage = args.val
    testPercentage = args.test

    meshFiles = [os.path.join(meshFolder, f) for f in sorted(os.listdir(meshFolder)) if os.path.isfile(os.path.join(meshFolder, f)) and os.path.splitext(f)[1] == ".obj"]
    
    # create directory to store newly generated aligned images
    if os.path.exists(dstFolder):
        shutil.rmtree(dstFolder)

    bRenderImage = False
    resize = 2
    os.mkdir(dstFolder)

    global counter

    for meshFile in meshFiles:
        print(meshFile)
        fileName = meshFile[meshFile.find('\\')+1:meshFile.find('.obj')]
        get8Views(meshFile)
        counter = 0
        for i in range(10):
            # create images for 10 random poses of this mesh
            bRenderImage = randomizeObject(meshFile, resize)
            if not bRenderImage:
                continue
            randomizeLight(lightType)
            # render the images now!
            renderImages(lightType)
            alignImages(dstFolder, fileName)

    # split the images into train, test and validation folders
    alignedImages = [os.path.join(dstFolder, f) for f in os.listdir(dstFolder) if os.path.isfile(os.path.join(dstFolder, f))]
    imgCount = len(alignedImages)
    valCount = int(valPercentage * imgCount / 100)
    testCount = int(testPercentage * imgCount / 100)
    print("valCount: ", valCount)
    print("testCount: ", testCount)
    #splitImages(dstFolder, valCount, testCount, alignedImages)