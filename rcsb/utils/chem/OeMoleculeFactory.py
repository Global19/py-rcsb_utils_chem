##
# File:    OeMoleculeFactory.py
# Author:  jdw
# Date:    2-Oct-2019
# Version: 0.001
#
# Updates:
# 2-Oct-2019  jdw adapted from OeBuildMol()
##
"""
Classes to build OE molecule objects from chemical component definition data.

"""

__docformat__ = "restructuredtext en"
__author__ = "John Westbrook"
__email__ = "john.westbrook@rcsb.org"
__license__ = "Apache 2.0"


import logging
from collections import defaultdict, namedtuple

from openeye import oechem
from openeye import oegraphsim
from openeye import oequacpac

from rcsb.utils.chem.PdbxChemComp import PdbxChemCompAtomIt, PdbxChemCompBondIt, PdbxChemCompDescriptorIt, PdbxChemCompIt
from rcsb.utils.chem.PdbxChemCompConstants import PdbxChemCompConstants


logger = logging.getLogger(__name__)

ComponentDetails = namedtuple("ComponentDetails", "ccId formula ifCharge")
ComponentAtom = namedtuple("ComponentAtom", "name aType isAromatic isChiral CIP fCharge")
ComponentBond = namedtuple("ComponentBond", "iType isAromatic CIP")
ComponentDescriptors = namedtuple("ComponentDescriptors", "smiles isoSmiles inchi inchiKey")
DescriptorInstance = namedtuple("DescriptorInstance", "type program")


class OeMoleculeFactory(object):
    """ Utility methods for constructing OEGraphMols from chemical component definition objects.
    """

    def __init__(self, verbose=False):
        self.__verbose = verbose
        self.__ccId = None
        self.__oeMol = None
        #
        # Source data categories objects from chemical component definitions.
        self.__dataContainer = None
        #
        self.__descriptorBuildType = None
        self.__descriptor = None
        #
        self.__isDefinitionSet = False
        #

    def __oeClear(self):
        #
        self.__oeMol = None
        self.__descriptorBuildType = None
        self.__descriptor = None

    def setQuiet(self):
        """Suppress OE warnings and processing errors
        """
        # oechem.OEThrow.SetLevel(5)
        oechem.OEThrow.SetLevel(oechem.OEErrorLevel_Quiet)

    def setDebug(self, flag):
        self.__verbose = flag

    def setChemCompDef(self, dataContainer):
        try:
            if dataContainer.exists("chem_comp"):
                ccIt = PdbxChemCompIt(dataContainer)
                for cc in ccIt:
                    ccId = cc.getId()
                self.__ccId = ccId
            else:
                self.__ccId = dataContainer.getName()

            self.__dataContainer = dataContainer
            if self.__dataContainer.exists("chem_comp_atom"):
                self.__isDefinitionSet = True
                return self.__ccId
            else:
                return None
        except Exception as e:
            logger.exception("Failing with %s", str(e))
        return None

    def setOeMol(self, inpOeMol, ccId):
        """  Load this object with an existing oeMOL()
        """
        self.__oeClear()
        self.__oeMol = oechem.OEGraphMol(inpOeMol)
        self.__ccId = ccId
        # self.getElementCounts()
        return ccId

    def setDescriptor(self, descriptor, molBuildType, ccId):
        self.__oeClear()
        self.__ccId = ccId
        self.__descriptorBuildType = molBuildType
        self.__descriptor = descriptor
        return ccId

    def addFingerPrints(self, fpTypeList):
        """ Add fingerprints (fpType) as data sections in the current molecule.

        Args:
            fpTypeList (list): list of fingerprint types [TREE,PATH,MACCS,CIRCULAR,LINGO].

        Returns:
            bool: True for success or False otherwise
        """
        if not self.__oeMol:
            return False
        myFpTypeList = fpTypeList if fpTypeList else []
        fpD = {
            "TREE": oegraphsim.OEFPType_Tree,
            "CIRCULAR": oegraphsim.OEFPType_Circular,
            "PATH": oegraphsim.OEFPType_Path,
            "MACCS": oegraphsim.OEFPType_MACCS166,
            "LINGO": oegraphsim.OEFPType_Lingo,
        }
        ret = True
        for fpType in myFpTypeList:
            if fpType in fpD:
                tag = "FP_" + fpType
                fp = oegraphsim.OEFingerPrint()
                ok = oegraphsim.OEMakeFP(fp, self.__oeMol, fpD[fpType])
                if ok and fp.IsValid():
                    self.__oeMol.SetData(tag, fp)
                    fpOk = True
                ret = ret and fpOk
        return ret

    def updateOePerceptions3D(self, oeMol, aromaticModel=oechem.OEAroModelOpenEye):
        oeMol.SetDimension(3)
        oechem.OEFindRingAtomsAndBonds(oeMol)
        oechem.OEPerceiveChiral(oeMol)
        #
        # Other aromatic models: oechem.OEAroModelMDL or OEAroModelDaylight or oechem.OEAroModelOpenEye
        #
        if aromaticModel is not None:
            oechem.OEAssignAromaticFlags(oeMol, aromaticModel)
        oechem.OE3DToInternalStereo(oeMol)
        return oeMol

    def updateOePerceptions2D(self, oeMol, aromaticModel=oechem.OEAroModelOpenEye):
        #
        # run standard perceptions --
        oechem.OEFindRingAtomsAndBonds(oeMol)
        oechem.OEPerceiveChiral(oeMol)
        #
        # Other aromatic models: oechem.OEAroModelMDL or OEAroModelDaylight or oechem.OEAroModelOpenEye
        #
        if aromaticModel is not None:
            oechem.OEAssignAromaticFlags(oeMol, aromaticModel)
        return oeMol

    def __transferAromaticFlagsOE(self, oeMol):
        """Manually assign/transfer aromatic flags from chemical component definition.

           Must follow other perceptions -
        """
        atIt = PdbxChemCompAtomIt(self.__dataContainer)
        ccAtomD = {}
        for at in atIt:
            atName = at.getName()
            isAromatic = at.isAromatic()
            ccAtomD[atName] = isAromatic
        ccBondD = {}
        bndIt = PdbxChemCompBondIt(self.__dataContainer)
        for bnd in bndIt:
            atIdI, atIdJ = bnd.getBond()
            isAromatic = bnd.isAromatic()
            ccBondD[(atIdI, atIdJ)] = isAromatic
            ccBondD[(atIdJ, atIdI)] = isAromatic
        #
        for atom in oeMol.GetAtoms():
            atName = atom.GetName()
            isAromatic = ccAtomD[atName]
            atom.SetAromatic(isAromatic)

        for bond in oeMol.GetBonds():
            atNameI = bond.GetBgn().GetName()
            atNameJ = bond.GetEnd().GetName()
            isAromatic = ccBondD[(atNameI, atNameJ)]
            bond.SetAromatic(isAromatic)
        #
        return oeMol

    def updateCIPStereoOE(self, oeMol):
        """ Manually assign OE CIP stereo perceptions for each atom and bond.

            Redundant of oechem.OE3DToInternalStereo(oeMol) -
        """
        for atom in oeMol.GetAtoms():
            cipV = oechem.OEPerceiveCIPStereo(oeMol, atom)
            if cipV in [oechem.OECIPAtomStereo_S, oechem.OECIPAtomStereo_R]:
                logger.info("%s CIP stereo is %r", atom.GetName(), cipV)
                oechem.OESetCIPStereo(oeMol, atom, cipV)
                cipV2 = oechem.OEPerceiveCIPStereo(oeMol, atom)
                logger.info("%s perceive after set CIP stereo (%r) is %r", atom.GetName(), atom.HasStereoSpecified(), cipV2)

        #
        for bond in oeMol.GetBonds():
            if bond.GetOrder() == 2:
                cipV = oechem.OEPerceiveCIPStereo(oeMol, bond)
                if cipV in [oechem.OECIPBondStereo_Z, oechem.OECIPBondStereo_E]:
                    logger.info("%s-%s CIP stereo is %r", bond.GetBgn().GetName(), bond.GetEnd().GetName(), cipV)
                    oechem.OESetCIPStereo(oeMol, bond, cipV)
                    cipV2 = oechem.OEPerceiveCIPStereo(oeMol, bond)
                    logger.info("%s-%s perceive after set CIP stereo (%r) is %r", bond.GetBgn().GetName(), bond.GetEnd().GetName(), bond.HasStereoSpecified(), cipV2)
        return oeMol

    def getGraphMolSuppressH(self):
        """ Return the current constructed OE molecule with hydrogens suppressed.
        """
        # OESuppressHydrogens(self.__oeMol, retainPolar=False,retainStereo=True,retainIsotope=True)
        oechem.OESuppressHydrogens(self.__oeMol)
        return self.__oeMol

    def getMol(self):
        """ Return a copy of the current constructed OE molecule.
        """
        return oechem.OEMol(self.__oeMol) if self.__oeMol else None

    def getGraphMol(self):
        """ Return a copy of current constructed Graph OE molecule.
        """
        return oechem.OEGraphMol(self.__oeMol) if self.__oeMol else None

    def getCanSMILES(self):
        """ Return the cannonical SMILES string derived from the current OD molecule.
        """
        return oechem.OECreateCanSmiString(self.__oeMol) if self.__oeMol else None

    def getIsoSMILES(self):
        """ Return the cannonical stereo SMILES string derived from the current OE molecule.
        """
        return oechem.OECreateIsoSmiString(self.__oeMol) if self.__oeMol else None

    def getFormula(self):
        """ Return the Hill order formulat  derived from the current OE molecule.
        """
        return oechem.OEMolecularFormula(self.__oeMol) if self.__oeMol else None

    def getFormalCharge(self):
        return oechem.OENetCharge(self.__oeMol) if self.__oeMol else 0

    def getInChIKey(self):
        """ Return the InChI key derived from the current OE molecule.
        """
        return oechem.OECreateInChIKey(self.__oeMol) if self.__oeMol else None

    def getInChI(self):
        """ Return the InChI string derived from the current OE molecule.
        """
        return oechem.OECreateInChI(self.__oeMol) if self.__oeMol else None

    def getTitle(self):
        """ Return the title assigned to the current OE molecule
        """
        return self.__oeMol.GetTitle() if self.__oeMol else None

    def getCcId(self):
        """ Return the CC id of this object -
        """
        return self.__ccId

    def setSimpleAtomNames(self):
        """
        """
        if self.__oeMol:
            for atom in self.__oeMol.GetAtoms():
                atom.SetIntType(atom.GetAtomicNum())
                atom.SetType(oechem.OEGetAtomicSymbol(atom.GetAtomicNum()))
            oechem.OETriposAtomNames(self.__oeMol)

    def getElementCounts(self, addExplicitHydrogens=False, useSymbol=False):
        """ Get the dictionary of element counts (eg. eD[iAtNo]=iCount).
        """
        eD = {}
        if self.__oeMol:
            if addExplicitHydrogens:
                if not oechem.OEAddExplicitHydrogens(self.__oeMol):
                    logger.warning("%s explict hydrogen addition fails", self.__ccId)
            # calculate from current oeMol
            try:
                eD = {}
                for atom in self.__oeMol.GetAtoms():
                    atNo = atom.GetAtomicNum()
                    if atNo not in eD:
                        eD[atNo] = 1
                    else:
                        eD[atNo] += 1
            except Exception:
                pass
        rD = {PdbxChemCompConstants.periodicTable[atNo - 1]: v for atNo, v in eD.items()} if useSymbol else eD
        #
        return rD

    def getOeMoleculeFeatures(self, filterHydrogens=False):
        """Get the essential features of the constructed OEMol for the input component.
        """
        formula = self.getFormula()
        # ccId = self.__ccId
        ccId = self.getTitle()
        ifCharge = oechem.OENetCharge(self.__oeMol)
        inchi = self.getInChI()
        inchiKey = self.getInChIKey()
        smiles = self.getCanSMILES()
        isoSmiles = self.getIsoSMILES()
        details = ComponentDetails(ccId=ccId, formula=formula, ifCharge=ifCharge)
        descriptors = ComponentDescriptors(smiles=smiles, isoSmiles=isoSmiles, inchi=inchi, inchiKey=inchiKey)
        typeCounts = defaultdict(int)
        ccAtomD = {}
        ccAtomIdD = {}
        ccNameTypeD = {}
        for atId, at in enumerate(self.__oeMol.GetAtoms(), 1):
            atName = at.GetName()
            atNo = at.GetAtomicNum()
            aType = PdbxChemCompConstants.periodicTable[atNo - 1]
            ccNameTypeD[atName] = aType
            if filterHydrogens and aType == "H":
                continue
            typeCounts[aType] += 1
            isAromatic = at.IsAromatic()
            isChiral = at.IsChiral()
            iCharge = at.GetFormalCharge()
            #
            cipStereo = None
            if at.HasStereoSpecified():
                cip = oechem.OEPerceiveCIPStereo(self.__oeMol, at)
                if cip == oechem.OECIPAtomStereo_S:
                    cipStereo = "S"
                if cip == oechem.OECIPAtomStereo_R:
                    cipStereo = "R"
                if cip == oechem.OECIPAtomStereo_NotStereo:
                    cipStereo = "?"
                if isChiral and cip == oechem.OECIPAtomStereo_UnspecStereo:
                    cipStereo = "?"

                #
                if cipStereo and cipStereo not in ["S", "R"]:
                    logger.error("%s (%s): Unexpected atom CIP stereo setting %r", ccId, atName, cipStereo)
            #
            ccAtomD[atName] = ComponentAtom(name=atName, aType=aType, isAromatic=isAromatic, isChiral=isChiral, CIP=cipStereo, fCharge=iCharge)
            ccAtomIdD[atId] = atName
        #
        ccBondD = {}
        for bnd in self.__oeMol.GetBonds():
            atNameI = bnd.GetBgn().GetName()
            atNameJ = bnd.GetEnd().GetName()
            if filterHydrogens and (ccNameTypeD[atNameI] == "H" or ccNameTypeD[atNameJ] == "H"):
                continue
            isAromatic = bnd.IsAromatic()
            iType = bnd.GetOrder()
            cipStereo = None
            if iType == 2:
                cip = oechem.OEPerceiveCIPStereo(self.__oeMol, bnd)
                if bnd.HasStereoSpecified():
                    if cip == oechem.OECIPBondStereo_E:
                        cipStereo = "E"
                    if cip == oechem.OECIPBondStereo_Z:
                        cipStereo = "Z"
                    if cip == oechem.OECIPBondStereo_NotStereo:
                        cipStereo = "?"
                    if cip == oechem.OECIPBondStereo_UnspecStereo:
                        cipStereo = "?"

            if cipStereo and cipStereo not in ["E", "Z"]:
                logger.error("%s (%s %s): Unexpected bond CIP stereo setting %r", ccId, atNameI, atNameJ, cipStereo)
            #
            ccBondD[(atNameI, atNameJ)] = ComponentBond(iType=iType, isAromatic=isAromatic, CIP=cipStereo)
        #
        ccD = {"details": details, "descriptors": descriptors, "atoms": ccAtomD, "bonds": ccBondD}
        return ccD

    # ----
    def buildRelated(self, limitPerceptions=False):
        """ Build the most "authorative" molecule from the chemical component definition and
        use this as a basis reference descriptors and related protomeric and tautomeric forms.
        This collection is designed to capture the chemical diversity within the component defintion
        as well as other reasonable chemical forms for search purposes.  The collection is returned
        as a nested dictionary of conventionally identified SMILES descriptors.

        Returns:
            dict: {'ccId|<buildType>': {'smiles': ..., 'inchi-key': ...}}
        """
        retD = {}
        if not self.__isDefinitionSet:
            return retD

        uniqSmilesD = {}
        try:
            for buildType in ["model-xyz", "oe-iso-smiles", "cactvs-iso-smiles", "inchi"]:
                ok = self.build(molBuildType=buildType, setTitle=True, limitPerceptions=limitPerceptions)
                if ok:
                    name = self.__ccId + "|" + "ref" if buildType == "model-xyz" else self.__ccId + "|" + buildType
                    smiles = self.getIsoSMILES()
                    inchiKey = self.getInChIKey()
                    formula = self.getFormula()
                    fCharge = self.getFormalCharge()
                    eleD = self.getElementCounts(addExplicitHydrogens=True, useSymbol=True)
                    if smiles and inchiKey and smiles not in uniqSmilesD:
                        uniqSmilesD[smiles] = True
                        retD[name] = {"name": name, "build-type": buildType, "smiles": smiles, "inchi-key": inchiKey, "formula": formula, "fcharge": fCharge, "elementCounts": eleD}
            for buildType in ["oe-smiles", "acdlabs-smiles", "cactvs-smiles"]:
                ok = self.build(molBuildType=buildType, setTitle=True, limitPerceptions=limitPerceptions)
                if ok:
                    name = self.__ccId + "|" + buildType
                    smiles = self.getCanSMILES()
                    inchiKey = self.getInChIKey()
                    formula = self.getFormula()
                    fCharge = self.getFormalCharge()
                    eleD = self.getElementCounts(addExplicitHydrogens=True, useSymbol=True)
                    if smiles and inchiKey and smiles not in uniqSmilesD:
                        uniqSmilesD[smiles] = True
                        retD[name] = {"name": name, "build-type": buildType, "smiles": smiles, "inchi-key": inchiKey, "formula": formula, "fcharge": fCharge, "elementCounts": eleD}
            # --- do charge and tautomer normalizatio on the model-xyz build
            ok = self.build(molBuildType="model-xyz", setTitle=True, limitPerceptions=limitPerceptions)
            if ok:
                upMol = self.getUniqueProtomerMol()
                if not upMol:
                    logger.warning("%s protomer and tautomer generation failed", self.__ccId)
                else:
                    name = self.__ccId + "|unique-protomer"
                    self.__oeMol = upMol
                    smiles = self.getIsoSMILES()
                    inchiKey = self.getInChIKey()
                    formula = self.getFormula()
                    fCharge = self.getFormalCharge()
                    eleD = self.getElementCounts(addExplicitHydrogens=True, useSymbol=True)
                    if smiles and inchiKey and smiles not in uniqSmilesD:
                        uniqSmilesD[smiles] = True
                        retD[name] = {
                            "name": name,
                            "build-type": "unique-protomer",
                            "smiles": smiles,
                            "inchi-key": inchiKey,
                            "formula": formula,
                            "fcharge": fCharge,
                            "elementCounts": eleD,
                        }
                    tautomerList = self.getTautomerMolList()
                    logger.debug("%s tautomer count %d", self.__ccId, len(tautomerList))
                    for ii, tMol in enumerate(tautomerList, 1):
                        if tMol:
                            label = "tautomer_%d" % ii
                            name = self.__ccId + "|" + label
                            self.__oeMol = tMol
                            smiles = self.getIsoSMILES()
                            inchiKey = self.getInChIKey()
                            formula = self.getFormula()
                            fCharge = self.getFormalCharge()
                            eleD = self.getElementCounts(addExplicitHydrogens=True, useSymbol=True)
                            if smiles and inchiKey and smiles not in uniqSmilesD:
                                uniqSmilesD[smiles] = True
                                retD[name] = {
                                    "name": name,
                                    "build-type": label,
                                    "smiles": smiles,
                                    "inchi-key": inchiKey,
                                    "formula": formula,
                                    "fcharge": fCharge,
                                    "elementCounts": eleD,
                                }

        except Exception as e:
            logger.info("Failing for %r with %s", self.__ccId, str(e))

        return retD

    # ----
    def build(self, molBuildType="model", setTitle=True, limitPerceptions=True, fallBackBuildType="model-xyz", normalize=False):
        try:
            if molBuildType in ["ideal-xyz", "model-xyz"]:
                oeMol = self.__build3D(molBuildType=molBuildType, setTitle=setTitle)
            elif molBuildType in ["connection-table"]:
                oeMol = self.__build2D(setTitle=setTitle)
            elif molBuildType in ["oe-iso-smiles", "oe-smiles", "acdlabs-smiles", "cactvs-iso-smiles", "cactvs-smiles", "inchi"]:
                oeMol = self.__buildFromDescriptor(self.__ccId, molBuildType, limitPerceptions=limitPerceptions, fallBackBuildType=fallBackBuildType)
            #
            if normalize:
                nMol = self.getUniqueProtomerMol(oeMol)
                self.__oeMol = nMol if nMol else oeMol
            else:
                self.__oeMol = oeMol
            return oeMol is not None
        except Exception as e:
            logger.info("Failing with %s", str(e))
        return False

    def __buildFromDescriptor(self, ccId, molBuildType, setTitle=True, limitPerceptions=True, fallBackBuildType="model-xyz", rebuildOnFailure=False):
        """Parse the input descriptor string and return a molecule object (OeGraphMol).

        Args:
            ccId (str): chemical component identifier
            molBuildType (str):  source data used to build molecule
            setTitle (bool): make chemical component identifer the molecular title
            limitPerceptions (bool): flag to limit the perceptions/transformations of input SMILES
            fallBackBuildType (str): fallback build type for missing descriptors  (Default:"model-xyz")

        Returns:
            object: OeGraphMol() object or None for failure

        """
        try:
            if molBuildType not in ["oe-iso-smiles", "oe-smiles", "acdlabs-smiles", "cactvs-iso-smiles", "cactvs-smiles", "inchi"]:
                logger.error("%s unexpected molBuildType %r", ccId, molBuildType)
                return None
            #
            ccId = self.__ccId
            #
            descr = self.__getDescriptor(ccId, molBuildType, fallBackBuildType=fallBackBuildType)
            if not descr:
                logger.warning("%r molBuildType %r missing descriptor", ccId, molBuildType)
                return None
            #
            oeMol = oechem.OEGraphMol()
            ok = True
            if molBuildType in ["oe-smiles", "oe-iso-smiles", "acdlabs-smiles", "cactvs-smiles", "cactvs-iso-smiles"]:
                smiles = descr
                if limitPerceptions:
                    # convert the descriptor string into a molecule
                    if not oechem.OEParseSmiles(oeMol, smiles, False, False):
                        logger.warning("%r parsing input failed for %r string %s", ccId, molBuildType, smiles)
                        ok = False
                        if self.__isDefinitionSet and rebuildOnFailure:
                            # Try again with a descriptor rebuild
                            smiles = self.__rebuildDescriptor(ccId, molBuildType, fallBackBuildType=fallBackBuildType)
                            ok = oechem.OEParseSmiles(oeMol, smiles, False, False)
                            if not ok:
                                logger.warning("%s regenerating %r failed from fallback build %r", ccId, molBuildType, fallBackBuildType)
                else:
                    logger.debug("Building with %s", smiles)
                    if not oechem.OESmilesToMol(oeMol, smiles):
                        logger.warning("%r converting input failed for %r string %s", ccId, molBuildType, smiles)
                        ok = False
                        if self.__isDefinitionSet and rebuildOnFailure:
                            # Try again with a descriptor rebuild
                            smiles = self.__rebuildDescriptor(ccId, molBuildType, fallBackBuildType=fallBackBuildType)
                            ok = oechem.OESmilesToMol(oeMol, smiles)
                            if not ok:
                                logger.warning("%s regenerating %r failed from fallback build %r", ccId, molBuildType, fallBackBuildType)

            elif molBuildType in ["inchi"]:
                inchi = descr
                logger.debug("Building with molBuildType %r descr %r ", molBuildType, descr)
                if limitPerceptions:
                    # convert the InChI string into a molecule
                    if not oechem.OEParseInChI(oeMol, inchi):
                        logger.warning("%r parsing input failed for InChI string %s", ccId, smiles)
                        ok = False
                        if self.__isDefinitionSet and rebuildOnFailure:
                            # Try again with a descriptor rebuild
                            inchi = self.__rebuildDescriptor(ccId, molBuildType, fallBackBuildType=fallBackBuildType)
                            ok = oechem.OEParseInChI(oeMol, inchi)
                            if not ok:
                                logger.warning("%s regenerating %r failed from fallback build %r", ccId, molBuildType, fallBackBuildType)
                else:
                    if not oechem.OEInChIToMol(oeMol, inchi):
                        logger.warning("%r converting input failed for InChI string %s", ccId, inchi)
                        ok = False
                        if self.__isDefinitionSet and rebuildOnFailure:
                            # Try again with a descriptor rebuild
                            inchi = self.__rebuildDescriptor(ccId, molBuildType, fallBackBuildType=fallBackBuildType)
                            ok = oechem.OEInChIToMol(oeMol, inchi)
                            if not ok:
                                logger.warning("%s regenerating %r failed from fallback build %r", ccId, molBuildType, fallBackBuildType)
            okT = True
            if ok:
                if setTitle:
                    oeMol.SetTitle(self.__ccId)
                oechem.OETriposAtomNames(oeMol)
                okT = self.__testDescriptorBuild(oeMol)
            #
            return oeMol if ok and okT else None
        except Exception as e:
            logger.exception("%r failing with %s", self.__ccId, str(e))
        return None

    def __testDescriptorBuild(self, oeMol):
        ok = False
        try:
            ok = oeMol.GetTitle() and oechem.OEMolecularFormula(oeMol) and oechem.OECreateIsoSmiString(oeMol)
            logger.debug("%s     Title %r", self.__ccId, oeMol.GetTitle())
            logger.debug("%s   Formula %r", self.__ccId, oechem.OEMolecularFormula(oeMol))
            logger.debug("%s ISOSMILES %r", self.__ccId, oechem.OECreateIsoSmiString(oeMol))
        except Exception as e:
            logger.error("%r failing with %s", self.__ccId, str(e))
        return ok

    def __getDescriptor(self, ccId, molBuildType, fallBackBuildType="model-xyz"):
        if molBuildType not in ["oe-iso-smiles", "oe-smiles", "acdlabs-smiles", "cactvs-iso-smiles", "cactvs-smiles", "inchi"]:
            logger.error("%s unexpected molBuildType %r", ccId, molBuildType)
            return None
        ret = None
        if not self.__isDefinitionSet:
            if molBuildType.upper() == self.__descriptorBuildType.upper():
                ret = self.__descriptor
        else:
            desIt = PdbxChemCompDescriptorIt(self.__dataContainer)
            for des in desIt:
                desBuildType = des.getMolBuildType()
                desText = des.getDescriptor()
                if molBuildType.upper() == desBuildType.upper():
                    ret = desText.strip()
            #
            # Try to create a missing descriptor if possible.
            if ret is None and molBuildType in ["oe-iso-smiles", "oe-smiles", "inchi"] and fallBackBuildType:
                try:
                    logger.info("%r missing descriptor for %r rebuilding using %r", ccId, molBuildType, fallBackBuildType)
                    ret = self.__rebuildDescriptor(ccId, molBuildType, fallBackBuildType=fallBackBuildType)
                except Exception as e:
                    logger.exception("%r descriptor rebuild failed using %r with %s", ccId, fallBackBuildType, str(e))

        return ret

    def __rebuildDescriptor(self, ccId, molBuildType, fallBackBuildType="ideal-xyz"):
        ok = self.build(molBuildType=fallBackBuildType)
        #
        descr = None
        if ok and molBuildType in ["oe-iso-smiles"]:
            descr = self.getIsoSMILES()
        elif ok and molBuildType in ["oe-smiles"]:
            descr = self.getCanSMILES()
        elif ok and molBuildType in ["inchi"]:
            descr = self.getInChI()
        else:
            logger.error("Rebuild failing for %r %r", ccId, molBuildType)
        #
        ret = descr.strip() if descr else None
        if not ret:
            logger.info("%s regenerating descriptor failed for buildType %r", ccId, fallBackBuildType)
        return ret

    def __build2D(self, setTitle=True):
        """  Build molecule using only atom and bond types, and associated annotations
             in a chemical component definition.
        """
        try:
            self.__oeClear()
            oeMol = oechem.OEGraphMol()
            if setTitle:
                oeMol.SetTitle(self.__ccId)
            aL = []
            i = 1
            # Atom index dictionary
            aD = {}
            eD = {}

            atomIt = PdbxChemCompAtomIt(self.__dataContainer)
            for ccAt in atomIt:
                atName = ccAt.getName()
                aD[atName] = i
                i += 1
                atNo = ccAt.getAtNo()
                if atNo not in eD:
                    eD[atNo] = 1
                else:
                    eD[atNo] += 1
                atType = ccAt.getType()
                fc = ccAt.getFormalCharge()
                chFlag = ccAt.isChiral()
                arFlag = ccAt.isAromatic()
                isotope = ccAt.getIsotope()
                leavingAtom = ccAt.getLeavingAtomFlag()

                oeAt = oeMol.NewAtom(atNo)
                oeAt.SetName(atName)
                oeAt.SetFormalCharge(fc)
                oeAt.SetStringData("pdbx_leaving_atom_flag", leavingAtom)
                oeAt.SetChiral(chFlag)
                oeAt.SetIsotope(isotope)
                oeAt.SetAromatic(arFlag)
                if chFlag:
                    st = ccAt.getCIPStereo()
                    if st == "S" or st == "R":
                        oeAt.SetStringData("StereoInfo", st)
                logger.debug("Atom - %s type %s atno %d isotope %d fc %d chFlag %r", atName, atType, atNo, isotope, fc, chFlag)
                aL.append(oeAt)

            bondIt = PdbxChemCompBondIt(self.__dataContainer)
            for ccBnd in bondIt:
                (at1, at2) = ccBnd.getBond()
                iat1 = aD[at1] - 1
                iat2 = aD[at2] - 1
                iType = ccBnd.getIntegerType()
                arFlag = ccBnd.isAromatic()
                logger.debug(" %s %d -- %s %d (%d)", at1, iat1, at2, iat2, iType)

                oeBnd = oeMol.NewBond(aL[iat1], aL[iat2], iType)
                oeBnd.SetAromatic(arFlag)
                if arFlag:
                    oeBnd.SetIntType(5)
                st = ccBnd.getStereo()
                if st == "E" or st == "Z":
                    oeBnd.SetStringData("StereoInfo", st)

            #
            oeMol = self.updateOePerceptions2D(oeMol, aromaticModel=None)
            # run standard perceptions --
            # oechem.OEFindRingAtomsAndBonds(oeMol)
            # oechem.OEPerceiveChiral(oeMol)

            for oeAt in oeMol.GetAtoms():
                st = oeAt.GetStringData("StereoInfo")
                if st == "R":
                    oechem.OESetCIPStereo(oeMol, oeAt, oechem.OECIPAtomStereo_R)
                elif st == "S":
                    oechem.OESetCIPStereo(oeMol, oeAt, oechem.OECIPAtomStereo_S)

            for oeBnd in oeMol.GetBonds():
                st = oeBnd.GetStringData("StereoInfo")
                if st == "E":
                    oechem.OESetCIPStereo(oeMol, oeBnd, oechem.OECIPBondStereo_E)
                elif st == "Z":
                    oechem.OESetCIPStereo(oeMol, oeBnd, oechem.OECIPBondStereo_Z)
            if self.__verbose:
                for ii, atm in enumerate(oeMol.GetAtoms()):
                    logger.debug("OeBuildMol.build2d - atom  %d %s", ii, atm.GetName())
            # JDW Add new
            # self.__transferAromaticFlagsOE(oeMol)
            return oeMol
        except Exception as e:
            logger.exception("Failing with %s", str(e))
        return None

    def __build3D(self, molBuildType, setTitle=True):
        """ Build molecule using only atom and bond types, and aromatic annotations
            in a chemical component defintion. Use the indicated 3D coordinate data
            to assign stereochemistry assignments.
        """
        try:
            self.__oeClear()
            oeMol = oechem.OEGraphMol()
            # oeMol = oechem.OEMol()
            #
            if setTitle:
                oeMol.SetTitle(self.__ccId)
            aL = []

            # Atom index dictionary
            aD = {}
            eD = {}
            i = 1

            atomIt = PdbxChemCompAtomIt(self.__dataContainer)
            for ccAt in atomIt:

                atName = ccAt.getName()
                aD[atName] = i
                i += 1
                atNo = ccAt.getAtNo()
                if atNo not in eD:
                    eD[atNo] = 1
                else:
                    eD[atNo] += 1

                atType = ccAt.getType()
                fc = ccAt.getFormalCharge()
                chFlag = ccAt.isChiral()
                arFlag = ccAt.isAromatic()
                isotope = ccAt.getIsotope()
                leavingAtom = ccAt.getLeavingAtomFlag()

                oeAt = oeMol.NewAtom(atNo)
                oeAt.SetName(atName)
                oeAt.SetFormalCharge(fc)
                oeAt.SetStringData("pdbx_leaving_atom_flag", leavingAtom)
                oeAt.SetChiral(chFlag)
                oeAt.SetIsotope(isotope)
                oeAt.SetAromatic(arFlag)
                tChk = oeAt.IsAromatic()
                if tChk != arFlag:
                    logger.info("%s inconsistent aromatic setting on %s", self.__ccId, atName)

                cTup = None
                if (molBuildType == "model-xyz") and ccAt.hasModelCoordinates():
                    cTup = ccAt.getModelCoordinates()
                    oeMol.SetCoords(oeAt, cTup)
                elif (molBuildType == "ideal-xyz") and ccAt.hasIdealCoordinates():
                    cTup = ccAt.getIdealCoordinates()
                    oeMol.SetCoords(oeAt, cTup)
                else:
                    pass

                logger.debug("Atom - %s type %s atno %d isotope %d fc %d (xyz) %r", atName, atType, atNo, isotope, fc, cTup)
                aL.append(oeAt)

            bondIt = PdbxChemCompBondIt(self.__dataContainer)
            for ccBnd in bondIt:
                (at1, at2) = ccBnd.getBond()
                iat1 = aD[at1] - 1
                iat2 = aD[at2] - 1
                iType = ccBnd.getIntegerType()
                logger.debug(" %s %d -- %s %d (%d)", at1, iat1, at2, iat2, iType)
                oeBnd = oeMol.NewBond(aL[iat1], aL[iat2], iType)
                atName1 = oeBnd.GetBgn().GetName()
                atName2 = oeBnd.GetEnd().GetName()
                logger.debug("%s - created bond %s %s", self.__ccId, atName1, atName2)

            #
            # run standard OE perceptions --
            #
            self.updateOePerceptions3D(oeMol)
            # Reset aromatic flags
            # self.__transferAromaticFlagsOE(oeMol)
            return oeMol
        except Exception as e:
            logger.exception("Failing with %s", str(e))
        return None

    #
    def getTautomerMolList(self, oeMol=None, maxTautomerAtoms=200):
        tautomerMolL = []
        tautomerOptions = oequacpac.OETautomerOptions()
        tautomerOptions.SetMaxTautomericAtoms(maxTautomerAtoms)
        logger.debug("Tautomer option max atoms = %r", tautomerOptions.GetMaxTautomericAtoms())
        pKaNorm = True
        inMol = oeMol if oeMol else self.__oeMol
        for tautomer in oequacpac.OEGetReasonableTautomers(inMol, tautomerOptions, pKaNorm):
            tautomerMolL.append(tautomer)
        return tautomerMolL

    def getUniqueProtomerMol(self, oeMol=None):
        inMol = oeMol if oeMol else self.__oeMol
        mol = oechem.OEGraphMol()
        ok = oequacpac.OEGetUniqueProtomer(mol, inMol)
        return mol if ok else None

    def getNeutralProtomerMol(self, oeMol=None):
        inMol = oeMol if oeMol else oechem.OEGraphMol(self.__oeMol)
        ok = oequacpac.OESetNeutralpHModel(inMol)
        return inMol if ok else None