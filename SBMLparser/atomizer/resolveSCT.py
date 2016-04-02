import marshal
import functools
import analyzeSBML
from collections import Counter, defaultdict
import itertools
from copy import deepcopy, copy
from utils.util import logMess
import atomizationAux as atoAux
import utils.pathwaycommons as pwcm


def memoize(obj):
    cache = obj.cache = {}

    @functools.wraps(obj)
    def memoizer(*args, **kwargs):
        key = marshal.dumps([args, kwargs])
        if key not in cache:
            cache[key] = obj(*args, **kwargs)
        return cache[key]
    return memoizer








def createSpeciesCompositionGraph(parser, database, configurationFile, namingConventions,
                                  speciesEquivalences=None, bioGridFlag=False):
    '''
    Main method for the SCT creation.

    It first does stoichiometry analysis, then lexical...
    '''
    _, rules, _ = parser.getReactions(atomize=True)
    molecules, _, _, _, _, _ = parser.getSpecies()
    database.sbmlAnalyzer = \
        analyzeSBML.SBMLAnalyzer(
            parser, configurationFile, namingConventions, speciesEquivalences, conservationOfMass=True)

    # classify reactions
    database.classifications, equivalenceTranslator, database.eequivalenceTranslator,\
        indirectEquivalenceTranslator, \
        adhocLabelDictionary, lexicalDependencyGraph, userEquivalenceTranslator = database.sbmlAnalyzer.classifyReactions(
            rules, molecules, {})
    database.reactionProperties = database.sbmlAnalyzer.getReactionProperties()
    # user defined and lexical analysis naming conventions are stored here
    database.reactionProperties.update(adhocLabelDictionary)

    database.translator, database.userLabelDictionary, \
        database.lexicalLabelDictionary, database.partialUserLabelDictionary = database.sbmlAnalyzer.getUserDefinedComplexes()
    database.dependencyGraph = {}
    database.alternativeDependencyGraph = {}

    # fill in the annotation dictionary
    database.annotationDict = parser.getFullAnnotation()
    # just molecule names without parenthesis
    strippedMolecules = [x.strip('()') for x in molecules]
    #database.annotationDict = {}

    # ###dependency graph
    # binding reactions
    for reaction, classification in zip(rules, database.classifications):
        bindingReactionsAnalysis(database.dependencyGraph,
                                 list(atoAux.parseReactions(reaction)), classification)
    # lexical dependency graph contains lexically induced binding compositions. atomizer gives preference to binding obtained this way as opposed to stoichiometry
    # stronger bounds on stoichiometry based binding can be defined in
    # reactionDefinitions.json.

    for element in lexicalDependencyGraph:

        if element in database.dependencyGraph and element not in database.userLabelDictionary:
            if len(lexicalDependencyGraph[element]) == 0:
                continue
            '''
            oldDependency = database.dependencyGraph[element]
            
            if sorted(lexicalDependencyGraph[element][0]) in [sorted(x) for x in oldDependency]:
                # if len(oldDependency) > 1:
                #    logMess('DEBUG:Atomization', 'Species {0} was confirmed to be {1} based on lexical information'.format(element,lexicalDependencyGraph[element]))
                database.dependencyGraph[
                    element] = lexicalDependencyGraph[element]
            else:
                # logMess('INFO:Atomization', 'Species {0} was determined to be {1} instead of {2} based on \
                # lexical information'.format(element,
                # lexicalDependencyGraph[element], oldDependency))
            '''
            if database.dependencyGraph[element] != []:
                database.alternativeDependencyGraph[element] = lexicalDependencyGraph[element]
            else:
                logMess('INFO:LAE009','{0}: being set to be a modification of cosntructed species {1}'.format(element,lexicalDependencyGraph[element][0]))
                atoAux.addToDependencyGraph(database.dependencyGraph,element,lexicalDependencyGraph[element][0])
        else:
            if element not in strippedMolecules:
                database.constructedSpecies.add(element)
            database.dependencyGraph[element] = lexicalDependencyGraph[element]
        # Check if I'm using a molecule that hasn't been used yet
        for dependencyCandidate in database.dependencyGraph[element]:
            for molecule in [x for x in dependencyCandidate if x not in database.dependencyGraph]:
                # this is a species that was not originally in the model. in case theres conflict later this is 
                # to indicate it is given less priority
                database.dependencyGraph[molecule] = []
    # user defined transformations
    for key in userEquivalenceTranslator:
        for namingEquivalence in userEquivalenceTranslator[key]:
            baseElement = min(namingEquivalence, key=len)
            modElement = max(namingEquivalence, key=len)
            if baseElement not in database.dependencyGraph:
                database.dependencyGraph[baseElement] = []
            atoAux.addToDependencyGraph(database.dependencyGraph, modElement,
                                 [baseElement])


    # database.eequivalence translator contains 1:1 equivalences
    # FIXME: do we need this update step or is it enough with the later one?
    # catalysis reactions
    '''
    for key in database.eequivalenceTranslator:
        for namingEquivalence in database.eequivalenceTranslator[key]:
            baseElement = min(namingEquivalence, key=len)
            modElement = max(namingEquivalence, key=len)
            if key != 'Binding':
                if baseElement not in database.dependencyGraph or database.dependencyGraph[baseElement] == []:
                    if modElement not in database.dependencyGraph or database.dependencyGraph[modElement] == []:
                        database.dependencyGraph[baseElement] = []
                    # do we have a meaningful reverse dependence?
                    # elif all([baseElement not in x for x in database.dependencyGraph[modElement]]):
                    #    atoAux.addToDependencyGraph(database.dependencyGraph,baseElement,[modElement])
                    #    continue

                        if baseElement in database.annotationDict and modElement in database.annotationDict:
                            baseSet = set([y for x in database.annotationDict[
                                          baseElement] for y in database.annotationDict[baseElement][x]])
                            modSet = set([y for x in database.annotationDict[
                                         modElement] for y in database.annotationDict[modElement][x]])
                            if len(baseSet.intersection(modSet)) > 0 or len(baseSet) == 0 or len(modSet) == 0:
                                atoAux.addToDependencyGraph(database.dependencyGraph, modElement,
                                                     [baseElement])
                            else:
                                logMess("ERROR:ANN201", "{0} and {1} have a direct correspondence according to reaction information however their annotations are completely different.".format(
                                    baseElement, modElement))
                        else:
                            atoAux.addToDependencyGraph(database.dependencyGraph, modElement,
                                                 [baseElement])
    '''
    # include user label information.
    for element in database.userLabelDictionary:
        if database.userLabelDictionary[element] in [0, [(0,)]]:
            database.dependencyGraph[element] = ['0']
        elif len(database.userLabelDictionary[element][0]) == 0 or element == \
                database.userLabelDictionary[element][0][0]:

            database.dependencyGraph[element] = []
        else:
            database.dependencyGraph[element] = [list(
                database.userLabelDictionary[element][0])]
            # If the user is introducing a new molecule term, add it to the SCT
            if database.userLabelDictionary[element][0][0] not in database.dependencyGraph:
                database.dependencyGraph[
                    database.userLabelDictionary[element][0][0]] = []

    # add species elements defined by the user into the naming convention
    # definition
    molecules.extend(['{0}()'.format(
        x) for x in database.userLabelDictionary if '{0}()'.format(x) not in molecules])
    # recalculate 1:1 equivalences now with binding information
    _, _, database.eequivalenceTranslator2,\
        _, adhocLabelDictionary, _, _ = database.sbmlAnalyzer.classifyReactions(
            rules, molecules, database.dependencyGraph)
    database.reactionProperties.update(adhocLabelDictionary)

    # update catalysis equivalences
    # catalysis reactions
    for key in database.eequivalenceTranslator2:
        for namingEquivalence in database.eequivalenceTranslator2[key]:

            baseElement = min(namingEquivalence, key=len)
            modElement = max(namingEquivalence, key=len)
            # dont overwrite user information
            if key != 'Binding' and modElement not in database.userLabelDictionary:
                if baseElement not in database.dependencyGraph:
                    database.constructedSpecies.add(baseElement)
                    database.dependencyGraph[baseElement] = []
                if modElement not in database.dependencyGraph or not [True for x in database.dependencyGraph[modElement] if baseElement in x and len(x) > 1]:
                    if baseElement in database.annotationDict and modElement in database.annotationDict:
                        baseSet = set([y for x in database.annotationDict[baseElement] for y in database.annotationDict[baseElement][x]])
                        modSet = set([y for x in database.annotationDict[
                                      modElement] for y in database.annotationDict[modElement][x]])
                        if len(baseSet.intersection(modSet)) > 0 or len(baseSet) == 0 or len(modSet) == 0:
                            if modElement not in database.dependencyGraph:
                                # if the entry doesnt exist from previous information accept this
                                atoAux.addToDependencyGraph(database.dependencyGraph, modElement, [baseElement])
                            else:
                                # otherwise add it to the lexical repository
                                atoAux.addToDependencyGraph(database.alternativeDependencyGraph, modElement, [baseElement])
                        else:
                            baseDB = set([x.split('/')[-2] for x in baseSet if 'identifiers.org' in x])
                            modDB = set([x.split('/')[-2] for x in modSet if 'identifiers.org' in x])
                            # it is still ok if they each refer to different databases
                            if len(baseDB.intersection(modDB)) == 0:
                                if modElement not in database.dependencyGraph:
                                    # if the entry doesnt exist from previous information accept this
                                    atoAux.addToDependencyGraph(database.dependencyGraph, modElement, [baseElement])
                                else:
                                    # otherwise add it to the lexical repository
                                    atoAux.addToDependencyGraph(database.alternativeDependencyGraph, modElement, [baseElement])
                            else:
                                logMess("WARNING:ANN201", "{0} and {1} have a direct correspondence according to reaction \
information however their annotations are completely different.".format(baseElement, modElement))
                    else:
                        atoAux.addToDependencyGraph(database.dependencyGraph, modElement,
                                             [baseElement])
                else:
                    logMess('WARNING:ATO114', 'Definition conflict between binding information {0} and lexical analyis {1} for molecule {2},\
choosing binding'.format(database.dependencyGraph[modElement], baseElement, modElement))

    # non lexical-analysis catalysis reactions
    if database.forceModificationFlag:
        for reaction, classification in zip(rules, database.classifications):
            preaction = list(atoAux.parseReactions(reaction))
            if len(preaction[0]) == 1 and len(preaction[1]) == 1:
                if (preaction[0][0] in [0, '0']) or (preaction[1][0] in [0, '0']):
                    continue
                if preaction[1][0].lower() in preaction[0][0].lower() or len(preaction[1][0]) < len(preaction[0][0]):
                    base = preaction[1][0]
                    mod = preaction[0][0]
                else:
                    mod = preaction[1][0]
                    base = preaction[0][0]
                if database.dependencyGraph[mod] == [] and mod not in database.userLabelDictionary:

                    if base in database.userLabelDictionary and \
                            database.userLabelDictionary[base] == 0:
                        continue
                    if mod in database.userLabelDictionary and \
                            database.userLabelDictionary[mod] == 0:
                        continue
                    if [mod] in database.dependencyGraph[base]:
                        continue

                    # can we just match it up through existing species instead of forcing a modification?
                    greedyMatch = database.sbmlAnalyzer.greedyModificationMatching(
                        mod, database.dependencyGraph.keys())

                    if greedyMatch not in [-1,-2, []]:
                        database.dependencyGraph[mod] = [greedyMatch]
                        if mod in database.alternativeDependencyGraph:
                            del database.alternativeDependencyGraph[mod]
                        logMess('INFO:LAE006','{0}: Mapped to {1} using lexical analysis/greedy matching'.format(mod, greedyMatch))
                        continue
                    

                    # if the annotations have no overlap whatsoever don't force
                    # this modifications
                    if base in database.annotationDict and mod in database.annotationDict:
                        baseSet = set([y for x in database.annotationDict[
                                      base] for y in database.annotationDict[base][x]])
                        modSet = set(
                            [y for x in database.annotationDict[mod] for y in database.annotationDict[mod][x]])
                        if(len(baseSet.intersection(modSet))) == 0 and len(baseSet) > 0 and len(modSet) > 0:
                            baseDB = set([x.split('/')[-2] for x in baseSet if 'identifiers.org' in x])
                            modDB = set([x.split('/')[-2] for x in modSet if 'identifiers.org' in x])
                            #we stil ahve to check that they both reference the same database
                            if len(baseDB.intersection(modDB)) > 0:
                                logMess("WARNING:ANN201", "{0} and {1} have a direct correspondence according to reaction \
information however their annotations are completely different.".format(base, mod))
                                continue
                    database.dependencyGraph[mod] = [[base]]

    '''
    #complex catalysis reactions
    for key in indirectEquivalenceTranslator:
        #first remove these entries from the dependencyGraph since
        #they are not true bindingReactions
        for namingEquivalence in indirectEquivalenceTranslator[key]:
            removedElement = ''
            tmp3 = deepcopy(namingEquivalence[1])
            if tmp3 in database.dependencyGraph[namingEquivalence[0][0]]:
                removedElement = namingEquivalence[0][0]
            elif tmp3 in database.dependencyGraph[namingEquivalence[0][1]]:
                removedElement = namingEquivalence[0][1]

            else:
                tmp3.reverse()
                if tmp3 in database.dependencyGraph[namingEquivalence[0][0]]:
                    removedElement = namingEquivalence[0][0]

                elif tmp3 in database.dependencyGraph[namingEquivalence[0][1]]:
                    removedElement = namingEquivalence[0][1]


            #then add the new, true dependencies
            #if its not supposed to be a basic element
            tmp = [x for x in namingEquivalence[1] if x not in namingEquivalence[2]]
            tmp.extend([x for x in namingEquivalence[2] if x not in namingEquivalence[1]])
            tmp2 = deepcopy(tmp)
            tmp2.reverse()
            ##TODO: map back for the elements in namingEquivalence[2]
            if tmp not in database.dependencyGraph[namingEquivalence[3][0]] \
                and tmp2 not in database.dependencyGraph[namingEquivalence[3][0]]:
                if sorted(tmp) == sorted(tmp3):
                    continue
                if all(x in database.dependencyGraph for x in tmp):
                    if removedElement in database.dependencyGraph:
                        database.dependencyGraph[removedElement].remove(tmp3)
                    logMess('INFO:Atomization','Removing {0}={1} and adding {2}={3} instead\
 from the dependency list since we determined it is not a true binding reaction based on lexical analysis'\
                    .format(removedElement,tmp3,namingEquivalence[3][0],tmp))
                    database.dependencyGraph[namingEquivalence[3][0]] = [tmp]
                else:
                    logMess('WARNING:Atomization','We determined that {0}={1} based on lexical analysis instead of \
{2}={3} (stoichiometry) but one of the constituent components in {1} is not a molecule so no action was taken'.format(namingEquivalence[3][0],
tmp,removedElement,tmp3))
    #user defined stuff
'''

    # stuff obtained from string similarity analysis
    for element in database.lexicalLabelDictionary:
        # similarity analysis has less priority than anything we discovered
        # before
        if element in database.dependencyGraph and \
                len(database.dependencyGraph[element]) > 0:
            continue

        if len(database.lexicalLabelDictionary[element][0]) == 0 or element == \
                database.lexicalLabelDictionary[element][0][0]:
            database.constructedSpecies.add(element)
            atoAux.addToDependencyGraph(database.dependencyGraph, element, [])
        else:
            # logMess('INFO:Atomization', ' added induced speciesStructure {0}={1}'
            #         .format(element, database.lexicalLabelDictionary[element][0]))
            database.dependencyGraph[element] = [list(
                database.lexicalLabelDictionary[element][0])]


    # Now let's go for annotation analysis and last resort stuff on the remaining orphaned molecules

    
    orphanedSpecies = [
        x for x in strippedMolecules if x not in database.dependencyGraph or database.dependencyGraph[x] == []]
    orphanedSpecies.extend([x for x in database.dependencyGraph if database.dependencyGraph[
                           x] == [] and x not in orphanedSpecies])

    # Fill SCT with annotations for those species that still dont have any
    # mapping


    annotationDependencyGraph, _ = fillSCTwithAnnotationInformation(
        orphanedSpecies, database.annotationDict, database)


    # use an empty dictionary if we wish to turn off annotation information in atomization
    #annotationDependencyGraph = {}

    for annotatedSpecies in annotationDependencyGraph:
        if len(annotationDependencyGraph[annotatedSpecies]) > 0 and annotatedSpecies not in database.userLabelDictionary:
            atoAux.addToDependencyGraph(
                database.dependencyGraph, annotatedSpecies, annotationDependencyGraph[annotatedSpecies][0])
            logMess('INFO:ANN004', 'Added equivalence from annotation information {0}={1}'.format(annotatedSpecies,
                                                                                                  annotationDependencyGraph[annotatedSpecies][0]))
            for element in annotationDependencyGraph[annotatedSpecies][0]:
                # in case one of the compositional elements is not yet in the
                # dependency graph
                if element not in database.dependencyGraph:
                    atoAux.addToDependencyGraph(database.dependencyGraph, element, [])


    nonOrphanedSpecies = [x for x in strippedMolecules if x not in orphanedSpecies]


    annotationDependencyGraph, _ = fillSCTwithAnnotationInformation(
        nonOrphanedSpecies, database.annotationDict, database,tentativeFlag=True)


    orphanedSpecies = [
        x for x in strippedMolecules if x not in database.dependencyGraph or database.dependencyGraph[x] == []]
    orphanedSpecies.extend([x for x in database.dependencyGraph if database.dependencyGraph[
                           x] == [] and x not in orphanedSpecies])


    orphanedSpecies.extend(database.constructedSpecies)
    strippedMolecules.extend([x.strip('()') for x in database.constructedSpecies])
    # TODO: merge both lists and use them as a tiebreaker for consolidation
    #completeAnnotationDependencyGraph, completePartialMatches = fillSCTwithAnnotationInformation(strippedMolecules, annotationDict, database, False)
    # pure lexical analysis for the remaining orphaned molecules
    tmpDependency, database.tmpEquivalence = database.sbmlAnalyzer.findClosestModification(
        orphanedSpecies, strippedMolecules, database)

    for species in tmpDependency:
        if species not in database.userLabelDictionary:
            if tmpDependency[species] == []:
                atoAux.addToDependencyGraph(database.dependencyGraph, species, [])
            for instance in tmpDependency[species]:
                atoAux.addToDependencyGraph(database.dependencyGraph, species, instance)
                if len(instance) == 1 and instance[0] not in database.dependencyGraph:
                    atoAux.addToDependencyGraph(database.dependencyGraph, instance[0], [])



    orphanedSpecies = [
        x for x in strippedMolecules if x not in database.dependencyGraph or database.dependencyGraph[x] == []]

    orphanedSpecies.extend([x for x in database.dependencyGraph if database.dependencyGraph[
                           x] == [] and x not in orphanedSpecies])

    orphanedSpecies.extend(database.constructedSpecies)
    # greedy lexical analysis for the remaining orhpaned species
    for reactant in orphanedSpecies:
        greedyMatch = database.sbmlAnalyzer.greedyModificationMatching(
            reactant, database.dependencyGraph.keys())
        if greedyMatch not in [-1,-2, []]:
            atoAux.addToDependencyGraph(database.dependencyGraph, reactant, greedyMatch)
            logMess('INFO:LAE006', 'Mapped {0} to {1} using lexical analysis/greedy matching'.format(reactant, greedyMatch))
    if len(database.constructedSpecies) > 0:
        logMess('WARNING:SCT131', 'The following species names do not appear in the original model but where created to have more appropiate naming conventions: [{0}]'.format(','.join(database.constructedSpecies)))


    # initialize and remove zero elements

    database.prunnedDependencyGraph, database.weights, unevenElementDict, database.artificialEquivalenceTranslator = \
        consolidateDependencyGraph(database.dependencyGraph, equivalenceTranslator,
                                   database.eequivalenceTranslator, database.sbmlAnalyzer, database)

    return database

def bindingReactionsAnalysis(dependencyGraph, reaction, classification):
    '''
    adds addBond based reactions based dependencies to the dependency graph

    >>> dg = dg2 = {}
    >>> bindingReactionsAnalysis(dg, [['A', 'B'], ['C']], 'Binding')
    >>> dg == {'A': [], 'C': [['A', 'B']], 'B': []}
    True
    >>> bindingReactionsAnalysis(dg2, [['C'], ['A', 'B']], 'Binding')
    >>> dg2 == {'A': [], 'C': [['A', 'B']], 'B': []}
    True
    '''
    totalElements = [item for sublist in reaction for item in sublist]
    for element in totalElements:
        atoAux.addToDependencyGraph(dependencyGraph, element, [])
        if classification == 'Binding':
            if len(reaction[1]) == 1 and element not in reaction[0]:
                atoAux.addToDependencyGraph(dependencyGraph, element, reaction[0])
            elif len(reaction[0]) == 1 and element not in reaction[1]:
                atoAux.addToDependencyGraph(dependencyGraph, element, reaction[1])



def fillSCTwithAnnotationInformation(orphanedSpecies, annotationDict, database, logResults=True,tentativeFlag=False):
        # annotation handling
    exactMatches = defaultdict(list)
    partialMatches = defaultdict(list)
    strongIntersectionMatches = defaultdict(list)
    intersectionMatches = defaultdict(list)
    # iterate over all pairs of orphaned species
    for combinationParticle in itertools.combinations(orphanedSpecies, 2):
            # compare annotations
        if combinationParticle[0] in annotationDict and combinationParticle[1] in annotationDict:

            sortedPair = sorted(list(combinationParticle), key=len)
            # get unary keys
            unaryAnnotation1 = [y for x in annotationDict[combinationParticle[0]] for y in annotationDict[
                combinationParticle[0]][x] if x in ['BQM_IS_DESCRIBED_BY', 'BQB_IS_VERSION_OF', 'BQB_IS','BQB_ENCODES'] and ('uniprot' in y or 'chebi' in y)]
            unaryAnnotation2 = [y for x in annotationDict[combinationParticle[1]] for y in annotationDict[
                combinationParticle[1]][x] if x in ['BQM_IS_DESCRIBED_BY', 'BQB_IS_VERSION_OF', 'BQB_IS','BQB_ENCODES'] and ('uniprot' in y or 'chebi' in y)]

            # get compositional keys
            compositionalAnnotation1 = [y for x in annotationDict[combinationParticle[0]] for y in annotationDict[
                combinationParticle[0]][x] if x in ['BQB_HAS_PART', 'BQB_HAS_VERSION'] and ('uniprot' in y or 'chebi' in y)]
            compositionalAnnotation2 = [y for x in annotationDict[combinationParticle[1]] for y in annotationDict[
                combinationParticle[1]][x] if x in ['BQB_HAS_PART', 'BQB_HAS_VERSION'] and ('uniprot' in y or 'chebi' in y)]
            # unary keys match
            if any([x in unaryAnnotation2 for x in unaryAnnotation1]):

                exactMatches[sortedPair[1]].append([sortedPair[0]])
            # one composes the other
            elif any([x in compositionalAnnotation1 for x in unaryAnnotation2]):
                #if combinationParticle[0] not in partialMatches:
                #    partialMatches[combinationParticle[0]].append([])
                partialMatches[combinationParticle[0]].append([combinationParticle[1]])

            elif any([x in compositionalAnnotation2 for x in unaryAnnotation1]):
                #if combinationParticle[1] not in partialMatches:
                #    partialMatches[combinationParticle[1]].append([])
                partialMatches[combinationParticle[1]].append([combinationParticle[0]])
            elif set(compositionalAnnotation1) == set(compositionalAnnotation2) and len([x in compositionalAnnotation2 for x in compositionalAnnotation1]) > 0:
                strongIntersectionMatches[sortedPair[1]].append([sortedPair[0]])
            # they intersect
            elif any([x in compositionalAnnotation2 for x in compositionalAnnotation1]):

                intersectionMatches[sortedPair[1]].append([sortedPair[0]])
                # intersectionMatches[combinationParticle[0]].append(combinationParticle[1])
    # create unary groups


    exactMatches = consolidateDependencyGraph(
        dict(exactMatches), {}, {}, database.sbmlAnalyzer, database, loginformation=False)[0]

    if logResults:
        for x in [y for y in exactMatches if len(exactMatches[y]) > 0]:
            if not tentativeFlag:
                logMess('INFO:ANN001', '{0}: can be the same as {1} according to annotation information. No action was taken'.format(
                    x, exactMatches[x]))
            else:

                if not (x in database.dependencyGraph and exactMatches[x][0][0] in database.dependencyGraph and database.dependencyGraph[x] == database.dependencyGraph[exactMatches[x][0][0]]):
                    logMess('WARNING:ANN101', '{0}: was determined to be the same as {1} according to annotation information. Please confirm from user information'.format(
                    x, exactMatches[x]))

    # create strong intersection groups

    strongIntersectionMatches = {x: strongIntersectionMatches[x] for x in strongIntersectionMatches if x not in partialMatches}
    strongIntersectionMatches.update(exactMatches)
    strongIntersectionMatches = consolidateDependencyGraph(dict(strongIntersectionMatches), {}, {}, database.sbmlAnalyzer, database, loginformation=False)[0]
    if logResults:
        for x in [y for y in strongIntersectionMatches if len(strongIntersectionMatches[y]) > 0]:
            if x not in exactMatches:
                if not tentativeFlag:
                    logMess('INFO:ANN002', '{0}: can exactly match {1} according to annotation information. No action was taken'.format(
                        x, strongIntersectionMatches[x]))
                else:
                    if not(x in database.dependencyGraph and strongIntersectionMatches[x][0][0] in database.dependencyGraph and \
                        database.dependencyGraph[x] == database.dependencyGraph[strongIntersectionMatches[x][0][0]]):
                        logMess('WARNING:ANN101', '{0}: was determined to exactly match {1} according to annotation information. Please confirm from user information'.format(
                        x, strongIntersectionMatches[x]))
    # create partial intersection groups
    '''
    intersectionMatches = {x: intersectionMatches[x] for x in intersectionMatches if x not in partialMatches and x not in strongIntersectionMatches}
    intersectionMatches.update(exactMatches)


    intersectionMatches = consolidateDependencyGraph(dict(intersectionMatches), {}, {}, database.sbmlAnalyzer, database, loginformation=False)[0]
    if logResults:
        for x in intersectionMatches:
            if x not in exactMatches:
                logMess('INFO:ANN002', '{0}: was determined to be partially match {1} according to annotation information.'.format(
                    x, intersectionMatches[x]))

    partialMatches = consolidateDependencyGraph(
        dict(partialMatches), {}, {}, database.sbmlAnalyzer, database, loginformation=False)[0]

    if logResults:
        for x in partialMatches:
            if partialMatches[x] != []:
                logMess('INFO:ANN003', '{0}: is thought to be partially composed of reactants {1} according to annotation information. Please verify stoichiometry'.format(
                    x, partialMatches[x]))

    # validAnnotationPairs.sort()

    intersectionMatches.update(strongIntersectionMatches)
    '''
    return intersectionMatches, partialMatches


def consolidateDependencyGraph(dependencyGraph, equivalenceTranslator,
                               equivalenceDictionary, sbmlAnalyzer, database, loginformation=True):
    """
    The second part of the Atomizer algorithm, once the lexical and stoichiometry information has been extracted
    it is time to state all elements of the system in unequivocal terms of their molecule types
    """

    equivalenceTranslator = {}
    def selectBestCandidate(reactant, candidates, dependencyGraph, sbmlAnalyzer,
                            equivalenceTranslator=equivalenceTranslator, equivalenceDictionary=equivalenceDictionary):


        tmpCandidates = []
        modifiedElementsPerCandidate = []
        unevenElements = []
        candidateDict = {}
        for individualAnswer in candidates:
            try:
                tmpAnswer = []
                flag = True
                if len(individualAnswer) == 1 and individualAnswer[0] == reactant:
                    continue
                modifiedElements = []
                for chemical in individualAnswer:

                    # we cannot handle tuple naming conventions for now
                    if type(chemical) == tuple:
                        flag = False
                        continue
                    # associate elements in the candidate description with their
                    # modified version
                    rootChemical = resolveDependencyGraph(
                        dependencyGraph, chemical)
                    mod = resolveDependencyGraph(dependencyGraph, chemical, True)
                    if mod != []:
                        modifiedElements.extend(mod)
                    for element in rootChemical:
                        if len(element) == 1 and type(element[0]) == tuple:
                            continue
                        if element == chemical:
                            tmpAnswer.append(chemical)
                        elif type(element) == tuple:
                            tmpAnswer.append(element)
                        else:
                            tmpAnswer.append(element[0])
                modifiedElementsPerCandidate.append(modifiedElements)
                if flag:
                    tmpAnswer = sorted(tmpAnswer)
                    tmpCandidates.append(tmpAnswer)
            except atoAux.CycleError:
                if loginformation:
                    logMess('ERROR:SCT221', '{0}:Dependency cycle found when mapping molecule to candidate {1}'.format(reactant, individualAnswer))
                continue
        # we cannot handle tuple naming conventions for now
        if len(tmpCandidates) == 0:
            # logMess('CRITICAL:Atomization', 'I dont know how to process these candidates and I have no \
            # way to make an educated guess. Politely refusing to translate
            # {0}={1}.'.format(reactant, candidates))
            return None, None, None
        originalTmpCandidates = deepcopy(tmpCandidates)
        # if we have more than one modified element for a single reactant
        # we can try to  choose the one that is most similar to the original
        # reactant
        # FIXME:Fails if there is a double modification
        newModifiedElements = {}
        #modifiedElementsCounter = Counter()
        modifiedElementsCounters = [Counter() for x in range(len(candidates))]
        # keep track of how many times we need to modify elements in the candidate description
        # FIXME: This only keeps track of the stuff in the fist candidates list
        for idx, modifiedElementsInCandidate in enumerate(modifiedElementsPerCandidate):
            for element in modifiedElementsInCandidate:
                if element[0] not in newModifiedElements or element[1] == reactant:
                    newModifiedElements[element[0]] = element[1]
                modifiedElementsCounters[idx][element[0]] += 1

        # actually modify elements and store final version in tmpCandidates
        # if tmpCandidates[1:] == tmpCandidates[:-1] or len(tmpCandidates) ==
        # 1:

        for tmpCandidate, modifiedElementsCounter in zip(tmpCandidates, modifiedElementsCounters):
            flag = True
            while flag:
                flag = False
                for idx, chemical in enumerate(tmpCandidate):
                    if modifiedElementsCounter[chemical] > 0:
                        modifiedElementsCounter[chemical] -= 1
                        tmpCandidate[idx] = newModifiedElements[chemical]
                        flag = True
                        break
        candidateDict = {
            tuple(x): y for x, y in zip(tmpCandidates, candidates)}
        bcan = []
        btmp = []
        borig = []
        # filter out those dependencies to the 0 element

        # if this is related to the zero element
        if len(tmpCandidates) == 1 and tmpCandidates[0] == ['0']:
            return ['0'], None, None

        for candidate, tmpcandidate, originaltmpcandidate in zip(candidates, tmpCandidates, originalTmpCandidates):
            if originaltmpcandidate != ['0']:
                bcan.append(candidate)
                btmp.append(tmpcandidate)
                borig.append(originaltmpcandidate)
        candidates = bcan
        tmpCandidates = btmp
        originalTmpCandidates = borig

        if len(tmpCandidates) == 0:
            return None, None, None

        # FIXME: I have no idea wtf this is doing so im commenting it out. i
        # think it's old code that is no longer ncessary
        '''
        # update candidate chemical references to their modified version if required
        if len(tmpCandidates) > 1:
            # temporal solution for defaulting to the first alternative
            totalElements = [y for x in tmpCandidates for y in x]
            elementDict = {}
            for word in totalElements:
                if word not in elementDict:
                    elementDict[word] = 0
                elementDict[word] += 1
            newTmpCandidates = [[]]
            for element in elementDict:
                if elementDict[element] % len(tmpCandidates) == 0:
                    newTmpCandidates[0].append(element)
                #elif elementDict[element] % len(tmpCandidates) != 0 and re.search('(_|^){0}(_|$)'.format(element),reactant):
                #    newTmpCandidates[0].append(element)
                #    unevenElements.append([element])
                else:
                    logMess('WARNING:Atomization', 'Are these actually the same? {0}={1}.'.format(reactant,candidates))
                    unevenElements.append(element)
            flag = True
            # FIXME:this should be done on newtmpCandidates instead of tmpcandidates
            while flag:
                flag = False
                for idx, chemical in enumerate(tmpCandidates[0]):
                    if chemical in newModifiedElements: #and newModifiedElements[chemical] in reactant:
                        tmpCandidates[0][idx] = newModifiedElements[chemical]
                        flag = True
                        break
        '''
        # if all the candidates are about modification changes to a complex
        # then try to do it through lexical analysis
        if all([len(candidate) == 1 for candidate in candidates]) and \
                candidates[0][0] != reactant and len(tmpCandidates[0]) > 1:
            if reactant is not None:
                pass

            # analyze based on standard modifications
            #lexCandidate, translationKeys, tmpequivalenceTranslator = sbmlAnalyzer.analyzeSpeciesModification(candidates[0][0], reactant, originalTmpCandidates[0])
            # print '++++'
            lexCandidate, translationKeys, tmpequivalenceTranslator = sbmlAnalyzer.analyzeSpeciesModification2(
                candidates[0][0], reactant, originalTmpCandidates[0])
            # lexCandidate, translationKeys, tmpequivalenceTranslator = sbmlAnalyzer.analyzeSpeciesModification(candidates[0][0], reactant, tmpCandidates[0])            # FIXME: this is iffy. is it always an append modification? could be prepend
            #lexCandidate = None
            if lexCandidate is not None:
                lexCandidate = tmpCandidates[0][
                    originalTmpCandidates[0].index(lexCandidate)]
                if translationKeys[0] + lexCandidate in dependencyGraph:
                    lexCandidateModification = translationKeys[0] + lexCandidate
                else:
                    lexCandidateModification = lexCandidate + translationKeys[0]

                for element in tmpequivalenceTranslator:
                    if element not in equivalenceTranslator:
                        equivalenceTranslator[element] = []
                    equivalenceTranslator[element].append((lexCandidate, lexCandidateModification))
                while lexCandidate in tmpCandidates[0]:
                    tmpCandidates[0].remove(lexCandidate)
                    tmpCandidates[0].append(lexCandidateModification)
                    break
                if lexCandidateModification not in dependencyGraph:
                    logMess('WARNING:SCT711', 'While analyzing {0}={1} we discovered equivalence {2}={3}, please verify \
this the correct behavior or provide an alternative for {0}'.format(reactant, tmpCandidates[0], lexCandidateModification, lexCandidate))
                dependencyGraph[lexCandidateModification] = [[lexCandidate]]

                return [tmpCandidates[0]], unevenElements, candidates

            else:
                fuzzyCandidateMatch = None
                '''
                if nothing else works and we know the result is a bimolecular
                complex and we know which are the basic reactants then try to
                do fuzzy string matching between the two.
                TODO: extend this to more than 2 molecule complexes.
                '''
                if len(tmpCandidates[0]) == 2:
                    tmpmolecules = []
                    tmpmolecules.extend(originalTmpCandidates[0])
                    tmpmolecules.extend(tmpCandidates[0])
                    # FIXME: Fuzzy artificial reaction is using old methods. Try to fix this
                    # or maybe not, no one was using it and when it was used it was wrong
                    # fuzzyCandidateMatch = sbmlAnalyzer.fuzzyArtificialReaction(originalTmpCandidates[0],[reactant],tmpmolecules)
                    fuzzyCandidateMatch = None
                if fuzzyCandidateMatch is not None:
                    # logMess('INFO:Atomization', 'Used fuzzy string matching from {0} to {1}'.format(reactant, fuzzyCandidateMatch))
                    return [fuzzyCandidateMatch], unevenElements, candidates
                else:
                    # map based on greedy matching
                    greedyMatch = sbmlAnalyzer.greedyModificationMatching(
                        reactant, dependencyGraph.keys())
                    if greedyMatch not in [-1, -2]:
                        return selectBestCandidate(reactant, [greedyMatch], dependencyGraph, sbmlAnalyzer)[0], unevenElements, candidates

                    # last ditch attempt using straighforward lexical analysis
                    tmpDependency, tmpEquivalence = sbmlAnalyzer.findClosestModification(
                        [reactant], dependencyGraph.keys(), database)
                    if reactant in tmpDependency and tmpDependency[reactant] in tmpCandidates[0]:
                        for element in tmpDependency:
                            if element not in dependencyGraph:
                                dependencyGraph[
                                    element] = tmpDependency[element]
                        for element in tmpEquivalence:
                            if element not in equivalenceDictionary:
                                equivalenceDictionary[element] = []
                            for equivalence in tmpEquivalence[element]:
                                if equivalence[0] not in equivalenceDictionary[element]:
                                    equivalenceDictionary[
                                        element].append(equivalence[0])
                        if len(tmpDependency.keys()) > 0:
                            return tmpDependency[reactant], unevenElements, candidates
                    # XXX: be careful of this change. This basically forces changes to happen
                    # the ive no idea whats going on branch
                    #modificationCandidates = {}
                    # if modificationCandidates == {}:

                    activeCandidates = []
                    for individualCandidate in tmpCandidates:
                        for tmpCandidate in individualCandidate:
                            activeQuery = None
                            uniprotkey = atoAux.getURIFromSBML(tmpCandidate,database.parser,  ['uniprot'])
                            if len(uniprotkey) > 0:
                                uniprotkey = uniprotkey[0].split('/')[-1]
                                activeQuery = pwcm.queryActiveSite(uniprotkey, None)
                            if activeQuery and len(activeQuery) > 0:
                                activeCandidates.append(tmpCandidate)
                                #enter modification information to database
                                #logMess('INFO:SCT051', '{0}:Determined that {0} has an active site for modication'.format(reactant, tmpCandidate))
                                #return [individualCandidate], unevenElements, candidates
                            # we want relevant biological names, its useless if they are too short
                            elif len(tmpCandidate) >= 3:
                            #else:
                                individualMajorCandidates = [y for x in candidates for y in x]
                                activeQuery =pwcm.queryActiveSite(tmpCandidate,None)
                                if activeQuery and len(activeQuery) > 0:
                                    otherMatches = [x for x in tmpCandidates[0] if x in activeQuery]
                                    if any([x for x in otherMatches if len(x) > len(tmpCandidate)]):
                                        continue
                                    activeCandidates.append(tmpCandidate)
                                #enter modification information to database
                                #logMess('INFO:SCT051', '{0}:Determined that {1} has an active site for modication'.format(reactant, tmpCandidate))
                                #return [individualCandidate], unevenElements, candidates
                    if len(activeCandidates) > 0:
                        if len(activeCandidates) == 1:
                            logMess('INFO:SCT051', '{0}:Determined through uniprot active site query that {1} has an active site for modication'.format(reactant, activeCandidates[0]))
                        if len(activeCandidates) > 1:
                            logMess('WARNING:SCT151','{0}:Determined through uniprot active site query that {1} have active site for modication. Defaulting to {2}'.format(reactant, activeCandidates, activeCandidates[0]))

                        for tmpCandidate, candidate in zip(tmpCandidates, candidates):
                            fuzzyList = sbmlAnalyzer.processAdHocNamingConventions(reactant, candidate[0], {}, False, dependencyGraph.keys())
                            if len(fuzzyList) > 0 and fuzzyList[0][1]:
                                if sbmlAnalyzer.testAgainstExistingConventions(fuzzyList[0][1], sbmlAnalyzer.namingConventions['modificationList']):
                                    database.eequivalenceTranslator2[fuzzyList[0][1]].append((activeCandidates[0], '{0}{1}'.format(activeCandidates, fuzzyList[0][1])))
                                else:
                                    database.eequivalenceTranslator2[fuzzyList[0][1]] = [(activeCandidates[0], '{0}{1}'.format(activeCandidates[0], fuzzyList[0][1]))]

                                if '{0}{1}'.format(activeCandidates[0], fuzzyList[0][1]) not in dependencyGraph:
                                    dependencyGraph['{0}{1}'.format(activeCandidates[0], fuzzyList[0][1])] = [[activeCandidates[0]]]

                                for idx, element in enumerate(tmpCandidate):
                                    if element == activeCandidates[0]:
                                        tmpCandidates[0][idx] = '{0}{1}'.format(activeCandidates[0], fuzzyList[0][1])
                                        break
                                return [tmpCandidates[0]], unevenElements, candidates



                    if len(tmpCandidates) != 1:
                        if not database.softConstraints:
                            if loginformation:
                                logMess('ERROR:SCT213', '{0}:Atomizer needs user information to determine which element is being modified among components {1}={2}.'.format(
                                reactant, candidates, tmpCandidates))
                            # print database.userLabelDictionary
                            return None, None, None
                    else:
                            
                        if not database.softConstraints:
                            if loginformation:
                                logMess('ERROR:SCT212', '{0}:Atomizer needs user information to determine which element is being modified among component species {1}={2}.'.format(
                                reactant, candidates, tmpCandidates))
                            return None, None, None
                        # print database.userLabelDictionary')
                    # return [tmpCandidates[0]], unevenElements

        elif len(tmpCandidates) > 1:
            # all candidates are equal/consistent
            if all(sorted(x) == sorted(tmpCandidates[0]) for x in tmpCandidates):
                tmpCandidates = [tmpCandidates[0]]
            elif reactant in database.alternativeDependencyGraph and loginformation:
                # candidates contradict each other but we have naming convention information in alternativeDependencyGraph
                if not all(sorted(x) == sorted(originalTmpCandidates[0]) for x in originalTmpCandidates):
                    if loginformation:
                        logMess('INFO:SCT001', '{0}:Using lexical analysis since stoichiometry gives non-consistent information naming({1})!=stoichiometry({2})'.format(reactant,
                                                                                                                                                           database.alternativeDependencyGraph[reactant][0], tmpCandidates))

                # else:
                #    print database.alternativeDependencyGraph[reactant],tmpCandidates,reactant
                #    logMess('INFO:Atomization', 'Using lexical analysis for species {0} =  {1} since stoichiometry gave conflicting information {2}'.format(reactant,
                # database.alternativeDependencyGraph[reactant][0],
                # tmpCandidates))

                # fallback to naming conventions
                candidate = database.alternativeDependencyGraph[reactant]
                # resolve naming convention candidate to its basic components
                # (molecule types)
                namingTmpCandidates = selectBestCandidate(
                    reactant, [candidate[0]], dependencyGraph, sbmlAnalyzer)[0]
                if not namingTmpCandidates:
                    logMess('ERROR:SCT211', '{0}:Cannot converge to solution, conflicting definitions {1}={2}'.format(
                            reactant, tmpCandidates, originalTmpCandidates))                    
                    return None, None, None
                if not any([sorted(subcandidate) == sorted(namingTmpCandidates[0]) for subcandidate in tmpCandidates]):
                    if loginformation:
                        logMess('WARNING:SCT112', '{0}:Stoichiometry analysis result in non self-consistent definitions but conflicts with lexical analysis stoichiometry({1})!= naming({2}). Selecting lexical analysis'.format(reactant,
                                                                                                                                                                                                                                          tmpCandidates, namingTmpCandidates))
                    atoAux.addAssumptions('lexicalVsstoch', (reactant, ('lexical', str(
                        namingTmpCandidates)), ('stoch', str(tmpCandidates)), ('original', str(originalTmpCandidates))), database.assumptions)

                tmpCandidates = namingTmpCandidates
                if loginformation:
                    database.alternativeDependencyGraph[reactant] = tmpCandidates
            elif all(sorted(x) == sorted(originalTmpCandidates[0]) for x in originalTmpCandidates):
                #the basic elements are the same but we are having trouble matching modifciations together
                sortedCandidates = sorted([([y for y in x if y in reactant], i) for i, x in enumerate(
                    tmpCandidates)], key=lambda z: [len(z[0]), sum([len(w) for w in z[0]])], reverse=True)
                if loginformation:
                    logMess('WARNING:SCT113', '{0}:candidates {1} agree on the basic components but naming conventions cannot determine  specific modifications. Selecting {2} based on longest partial match'.format(
                        reactant, tmpCandidates, tmpCandidates[sortedCandidates[0][1]]))
                replacementCandidate = [tmpCandidates[sortedCandidates[0][1]]]
                atoAux.addAssumptions('lexicalVsstoch', (reactant, ('current', str(replacementCandidate)), ('alternatives', str(
                    [x for x in tmpCandidates if x != replacementCandidate[0]])), ('original', str(originalTmpCandidates))), database.assumptions)
                tmpCandidates = replacementCandidate
            else:
                tmpCandidates2 = [x for x in tmpCandidates if all(y not in x for y in database.constructedSpecies)]
                # if we had constructed species disregard those since they are introducing noise
                if len(tmpCandidates2) > 0 and len(tmpCandidates) != len(tmpCandidates2):
                    return selectBestCandidate(reactant, tmpCandidates2, dependencyGraph, sbmlAnalyzer)
                elif len(tmpCandidates2) == 0:
                    #the differences is between species that we created so its the LAE fault. Just choose one.
                    tmpCandidates.sort(key=len)
                    tmpCandidates = [tmpCandidates[0]]
                else:
                    if loginformation:
                        logMess('ERROR:SCT211', '{0}:Cannot converge to solution, conflicting definitions {1}={2}'.format(
                        reactant, tmpCandidates, originalTmpCandidates))
                    return None, None, None
        elif reactant in database.alternativeDependencyGraph and loginformation:
            # there is one stoichionetry candidate but the naming convention
            # and the stoichionetry dotn agree
            if tmpCandidates[0] != database.alternativeDependencyGraph[reactant][0]:
                # make sure the naming convention is resolved to basic
                # omponents
                candidate = database.alternativeDependencyGraph[reactant]
                # this is to avoid recursion
                if loginformation:
                    del database.alternativeDependencyGraph[reactant]
                namingtmpCandidates = selectBestCandidate(
                    reactant, [candidate[0]], dependencyGraph, sbmlAnalyzer)[0]

                # if they still disagree print error and use stoichiometry
                if namingtmpCandidates and tmpCandidates[0] != namingtmpCandidates[0]:

                    if loginformation:
                        if namingtmpCandidates[0][0] in database.constructedSpecies:
                            namingTmpCandidates = tmpCandidates

                        else:
                            database.alternativeDependencyGraph[reactant] = namingtmpCandidates
                            logMess('WARNING:SCT111', '{0}:conflicting definitions between stoichiometry ({1}) and naming conventions {2}. Choosing the latter'.format(
                                    reactant, tmpCandidates[0], database.alternativeDependencyGraph[reactant]))
                    tmpCandidates = namingtmpCandidates
                    atoAux.addAssumptions('lexicalVsstoch', (reactant, ('stoch', str(tmpCandidates)), ('lexical', str(
                        namingtmpCandidates)), ('original', str(originalTmpCandidates))), database.assumptions)
                    for element in tmpCandidates[0]:
                        if element not in prunnedDependencyGraph:
                            # elemental species that were not used anywhere
                            # else but for those entries discovered through
                            # naming conventions
                            prunnedDependencyGraph[element] = []
                elif not namingtmpCandidates:
                    if loginformation:
                        logMess('WARNING:SCT121','{0}:could not resolve naming({1}) into a viable compositional candidate. choosing stoichiometry({2})'.format(reactant,candidate,tmpCandidates[0]))
        originalCandidateName = candidateDict[tuple(tmpCandidates[0])] if tuple(
            tmpCandidates[0]) in candidateDict else None
        return [tmpCandidates[0]], unevenElements, originalCandidateName

    prunnedDependencyGraph = deepcopy(dependencyGraph)

    tempMergedDependencyGraph = deepcopy(prunnedDependencyGraph)
    for element in database.alternativeDependencyGraph:
        if element in tempMergedDependencyGraph:
            tempMergedDependencyGraph[element].extend(database.alternativeDependencyGraph[element])
    weights = weightDependencyGraph(tempMergedDependencyGraph)



    #raise Exception

    unevenElementDict = {}
    for element in weights:
        candidates = [x for x in prunnedDependencyGraph[element[0]]]
        if len(candidates) == 1 and type(candidates[0][0]) == tuple:
            prunnedDependencyGraph[element[0]] = []
        if len(candidates) >= 1:
            candidates, uneven, originalCandidate = selectBestCandidate(
                element[0], candidates, prunnedDependencyGraph, sbmlAnalyzer)
            #except CycleError:
            #    candidates = None
            #    uneven = []
            if uneven != []:
                unevenElementDict[element[0]] = (uneven)
        if candidates is None:
            prunnedDependencyGraph[element[0]] = []
        else:
            prunnedDependencyGraph[element[0]] = [
                sorted(x) for x in candidates]

    weights = weightDependencyGraph(prunnedDependencyGraph)
    return prunnedDependencyGraph, weights, unevenElementDict, equivalenceTranslator


@memoize
def measureGraph(element, path):
    '''
    Calculates the weight of individual paths as the sum of the weights of the individual candidates plus the number of 
    candidates. The weight of an individual candidate is equal to the sum of strings contained in that candidate different
    from the original reactant
    >>> measureGraph('Trash',['0'])
    1
    >>> measureGraph('EGF',[['EGF']])
    2
    >>> measureGraph('EGFR_P',[['EGFR']])
    3
    >>> measureGraph('EGF_EGFR', [['EGF', 'EGFR']])
    4
    >>> measureGraph('A_B_C',[['A', 'B_C'], ['A_B', 'C']])
    7
    ''' 
    counter = 1
    for x in path:
        if type(x) == list or type(x) == tuple:
            counter += measureGraph(element, x)
        elif x != '0' and x != element:
            counter += 1
    return counter



def weightDependencyGraph(dependencyGraph):
    '''
    Given a dependency Graph it will return a list indicating the weights of its elements
    a path is calculated 
    >>> weightDependencyGraph({'EGF_EGFR_2':[['EGF_EGFR','EGF_EGFR']],'EGF_EGFR':[['EGF','EGFR']],'EGFR':[],'EGF':[],\
    'EGFR_P':[['EGFR']],'EGF_EGFR_2_P':[['EGF_EGFR_2']]})
    [['EGF', 2], ['EGFR', 2], ['EGFR_P', 4], ['EGF_EGFR', 5], ['EGF_EGFR_2', 9], ['EGF_EGFR_2_P', 10]]
    >>> dependencyGraph2 = {'A':[],'B':[],'C':[],'A_B':[['A','B']],'B_C':[['B','C']],'A_B_C':[['A_B','C'],['B_C','A']]}
    >>> weightDependencyGraph(dependencyGraph2)
    [['A', 2], ['C', 2], ['B', 2], ['B_C', 5], ['A_B', 5], ['A_B_C', 13]]
    '''
    weights = []
    for element in dependencyGraph:
        path = resolveDependencyGraph(dependencyGraph, element)
        try:
            path2 = resolveDependencyGraph(dependencyGraph, element, True)
        except atoAux.CycleError:
            path2 = []
        weight = measureGraph(element, path) + len(path2)
        weights.append([element, weight])

    weights = sorted(weights, key=lambda rule: (rule[1], len(rule[0])))
    return weights

def resolveDependencyGraph(dependencyGraph, reactant, withModifications=False):
    '''
    Given a full species composition table and a reactant it will return an unrolled list of the molecule types
    (elements with no dependencies that define this reactant). The classification to the original candidates is lost
    since elements are fully unrolled. For getting dependencies keeping candidate consistency use consolidateDependencyGraph
    instead
    
    Args:
        withModifications (bool): returns a list of the 1:1 transformation relationships found in the path to this graph


    >>> dependencyGraph = {'EGF_EGFR_2':[['EGF_EGFR','EGF_EGFR']],'EGF_EGFR':[['EGF','EGFR']],'EGFR':[],'EGF':[],\
    'EGFR_P':[['EGFR']],'EGF_EGFR_2_P':[['EGF_EGFR_2']]}
    >>> dependencyGraph2 = {'A':[],'B':[],'C':[],'A_B':[['A','B']],'B_C':[['B','C']],'A_B_C':[['A_B','C'],['B_C','A']]}
    >>> resolveDependencyGraph(dependencyGraph, 'EGFR')
    [['EGFR']]
    >>> resolveDependencyGraph(dependencyGraph, 'EGF_EGFR')
    [['EGF'], ['EGFR']]
    >>> sorted(resolveDependencyGraph(dependencyGraph, 'EGF_EGFR_2_P'))
    [['EGF'], ['EGF'], ['EGFR'], ['EGFR']]
    
    >>> sorted(resolveDependencyGraph(dependencyGraph, 'EGF_EGFR_2_P', withModifications=True))
    [('EGF_EGFR_2', 'EGF_EGFR_2_P')]
    >>> sorted(resolveDependencyGraph(dependencyGraph2,'A_B_C'))
    [['A'], ['A'], ['B'], ['B'], ['C'], ['C']]
    '''
    topCandidate = resolveDependencyGraphHelper(
        dependencyGraph, reactant, [], withModifications)
    return topCandidate

@memoize
def resolveDependencyGraphHelper(dependencyGraph, reactant, memory,
                                 withModifications=False):
    """
    Helper function for resolveDependencyGraph that adds a memory field to resolveDependencyGraphHelper to avoid 
    cyclical definitions problems 

    >>> dependencyGraph = {'EGF_EGFR_2':[['EGF_EGFR','EGF_EGFR']],'EGF_EGFR':[['EGF','EGFR']],'EGFR':[],'EGF':[],\
    'EGFR_P':[['EGFR']],'EGF_EGFR_2_P':[['EGF_EGFR_2']]}
    >>> dependencyGraph2 = {'A':[],'B':[],'C':[],'A_B':[['A','B']],'B_C':[['B','C']],'A_B_C':[['A_B','C'],['B_C','A']]}
    >>> sorted(resolveDependencyGraphHelper(dependencyGraph, 'EGF_EGFR_2_P',[]))
    [['EGF'], ['EGF'], ['EGFR'], ['EGFR']]
   
    >>> sorted(resolveDependencyGraphHelper(dependencyGraph, 'EGF_EGFR_2_P', [], withModifications=True))
    [('EGF_EGFR_2', 'EGF_EGFR_2_P')]

    >>> sorted(resolveDependencyGraphHelper(dependencyGraph2, 'A_B_C', []))
    [['A'], ['A'], ['B'], ['B'], ['C'], ['C']]

    >>> dependencyGraph3 = {'C1': [['C2']],'C2':[['C3']],'C3':[['C1']]}
    >>> resolveDependencyGraphHelper(dependencyGraph3, 'C3', [], withModifications=True)
    Traceback (innermost last):
      File "<stdin>", line 1, in ?
    CycleError
    """
    
    result = []
    # if type(reactant) == tuple:
    #    return []
    if reactant not in dependencyGraph or dependencyGraph[reactant] == [] or \
            dependencyGraph[reactant] == [[reactant]]:
        if not withModifications:
            result.append([reactant])
    else:
        for option in dependencyGraph[reactant]:
            tmp = []
            for element in option:
                if element in memory and not withModifications:
                    result.append([element])
                    continue
                elif element in memory:
                    #logMess(
                    #    'ERROR:SCT201', 'dependency cycle detected on {0}'.format(element))
                    raise atoAux.CycleError(memory)
                baseElement = resolveDependencyGraphHelper(dependencyGraph, element,
                                                           memory + [element], withModifications)
                if baseElement is not None:
                    tmp.extend(baseElement)
            # if not withModifications:
            result.extend(tmp)
            if len(option) == 1 and withModifications and option[0] != reactant:
                result.append((option[0], reactant))
    return result
